// Package cache fronts API responses with Redis. It speaks the Redis
// Serialization Protocol (RESP) directly over TCP using only the standard
// library, so the project has no third-party dependencies.
package cache

import (
	"bufio"
	"context"
	"fmt"
	"net"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// Cache is the interface the API depends on. Implementations must be safe
// for concurrent use and must never fail a request when caching fails.
type Cache interface {
	// Get returns the cached value and whether it was present.
	Get(ctx context.Context, key string) ([]byte, bool)
	// Set stores value for ttl. Errors are swallowed by implementations:
	// caching is best-effort.
	Set(ctx context.Context, key string, value []byte, ttl time.Duration)
}

// NoopCache disables caching (used when Redis is unavailable and in tests).
type NoopCache struct{}

func (NoopCache) Get(context.Context, string) ([]byte, bool)         { return nil, false }
func (NoopCache) Set(context.Context, string, []byte, time.Duration) {}

// RedisCache is a minimal RESP client supporting PING, GET and SETEX.
// Each operation opens a short-lived connection, keeping the client simple
// and safe for the request rates this demo serves. When Password is set
// the client sends AUTH first; when DB is non-zero it sends SELECT after
// AUTH, so redis:// URLs with credentials and a database index work.
type RedisCache struct {
	Addr     string
	Password string
	DB       int
	Timeout  time.Duration
}

// ParseRedisURL parses a redis:// URL (redis://[:password@]host:port[/db])
// into address, password and database index. rediss:// (TLS) is rejected:
// this minimal client does not do TLS. A bare "host:port" is also accepted
// and treated as address with no password.
func ParseRedisURL(rawurl string) (addr, password string, db int, err error) {
	if rawurl == "" {
		return "", "", 0, fmt.Errorf("empty redis url")
	}
	if !strings.Contains(rawurl, "://") {
		return rawurl, "", 0, nil
	}
	u, err := url.Parse(rawurl)
	if err != nil {
		return "", "", 0, fmt.Errorf("parse redis url: %w", err)
	}
	switch u.Scheme {
	case "redis":
	case "rediss":
		return "", "", 0, fmt.Errorf("rediss:// (TLS) is not supported by this client")
	default:
		return "", "", 0, fmt.Errorf("unsupported redis url scheme %q", u.Scheme)
	}
	host := u.Hostname()
	port := u.Port()
	if port == "" {
		port = "6379"
	}
	addr = net.JoinHostPort(host, port)
	if u.User != nil {
		if pw, ok := u.User.Password(); ok {
			password = pw
		}
	}
	if p := strings.TrimPrefix(u.Path, "/"); p != "" {
		db, err = strconv.Atoi(p)
		if err != nil || db < 0 {
			return "", "", 0, fmt.Errorf("invalid redis db index %q", p)
		}
	}
	return addr, password, db, nil
}

// authenticate sends AUTH (when a password is set) and SELECT (when DB is
// non-zero) on a fresh connection. It must run before the actual command.
func (c *RedisCache) authenticate(conn net.Conn, r *bufio.Reader) error {
	if c.Password != "" {
		if err := writeCommand(conn, "AUTH", c.Password); err != nil {
			return err
		}
		if _, _, err := readReply(r); err != nil {
			return err
		}
	}
	if c.DB != 0 {
		if err := writeCommand(conn, "SELECT", strconv.Itoa(c.DB)); err != nil {
			return err
		}
		if _, _, err := readReply(r); err != nil {
			return err
		}
	}
	return nil
}

func (c *RedisCache) dial(ctx context.Context) (net.Conn, *bufio.Reader, error) {
	d := net.Dialer{Timeout: c.timeout()}
	conn, err := d.DialContext(ctx, "tcp", c.Addr)
	if err != nil {
		return nil, nil, err
	}
	return conn, bufio.NewReader(conn), nil
}

func (c *RedisCache) timeout() time.Duration {
	if c.Timeout > 0 {
		return c.Timeout
	}
	return 2 * time.Second
}

// writeCommand encodes args as a RESP array of bulk strings.
func writeCommand(conn net.Conn, args ...string) error {
	var b strings.Builder
	fmt.Fprintf(&b, "*%d\r\n", len(args))
	for _, a := range args {
		fmt.Fprintf(&b, "$%d\r\n%s\r\n", len(a), a)
	}
	_, err := conn.Write([]byte(b.String()))
	return err
}

// readReply parses one RESP reply. It returns (value, isNil, err).
func readReply(r *bufio.Reader) (string, bool, error) {
	line, err := r.ReadString('\n')
	if err != nil {
		return "", false, err
	}
	line = strings.TrimRight(line, "\r\n")
	if line == "" {
		return "", false, fmt.Errorf("empty redis reply")
	}
	switch line[0] {
	case '+':
		return line[1:], false, nil
	case '-':
		return "", false, fmt.Errorf("redis error: %s", line[1:])
	case ':':
		return line[1:], false, nil
	case '$':
		n, err := strconv.Atoi(line[1:])
		if err != nil {
			return "", false, err
		}
		if n < 0 {
			return "", true, nil // nil bulk string
		}
		buf := make([]byte, n+2) // payload + trailing CRLF
		if _, err := readFull(r, buf); err != nil {
			return "", false, err
		}
		return string(buf[:n]), false, nil
	default:
		return "", false, fmt.Errorf("unexpected redis reply: %q", line)
	}
}

func readFull(r *bufio.Reader, buf []byte) (int, error) {
	total := 0
	for total < len(buf) {
		n, err := r.Read(buf[total:])
		total += n
		if err != nil {
			return total, err
		}
	}
	return total, nil
}

// Ping verifies the server answers.
func (c *RedisCache) Ping(ctx context.Context) error {
	conn, r, err := c.dial(ctx)
	if err != nil {
		return err
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(c.timeout()))
	if err := c.authenticate(conn, r); err != nil {
		return err
	}
	if err := writeCommand(conn, "PING"); err != nil {
		return err
	}
	val, _, err := readReply(r)
	if err != nil {
		return err
	}
	if val != "PONG" {
		return fmt.Errorf("unexpected PING reply: %q", val)
	}
	return nil
}

// Get fetches a cached value.
func (c *RedisCache) Get(ctx context.Context, key string) ([]byte, bool) {
	conn, r, err := c.dial(ctx)
	if err != nil {
		return nil, false
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(c.timeout()))
	if err := c.authenticate(conn, r); err != nil {
		return nil, false
	}
	if err := writeCommand(conn, "GET", key); err != nil {
		return nil, false
	}
	val, isNil, err := readReply(r)
	if err != nil || isNil {
		return nil, false
	}
	return []byte(val), true
}

// Set stores a value with a TTL.
func (c *RedisCache) Set(ctx context.Context, key string, value []byte, ttl time.Duration) {
	secs := int(ttl / time.Second)
	if secs < 1 {
		secs = 1
	}
	conn, r, err := c.dial(ctx)
	if err != nil {
		return
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(c.timeout()))
	if err := c.authenticate(conn, r); err != nil {
		return
	}
	if err := writeCommand(conn, "SETEX", key, strconv.Itoa(secs), string(value)); err != nil {
		return
	}
	_, _, _ = readReply(r)
}
