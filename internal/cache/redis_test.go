package cache

import (
	"bufio"
	"context"
	"fmt"
	"net"
	"strings"
	"sync"
	"testing"
	"time"
)

// fakeRedis is a tiny in-process RESP server supporting PING, GET, SETEX.
// It lets the client be tested without a real Redis binary.
type fakeRedis struct {
	mu   sync.Mutex
	data map[string]string
	ln   net.Listener
}

func startFakeRedis(t *testing.T) (*fakeRedis, string) {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	f := &fakeRedis{data: map[string]string{}, ln: ln}
	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			go f.handle(conn)
		}
	}()
	t.Cleanup(func() { ln.Close() })
	return f, ln.Addr().String()
}

func (f *fakeRedis) handle(conn net.Conn) {
	defer conn.Close()
	r := bufio.NewReader(conn)
	for {
		args, err := readCommand(r)
		if err != nil {
			return
		}
		if len(args) == 0 {
			continue
		}
		switch strings.ToUpper(args[0]) {
		case "PING":
			fmt.Fprint(conn, "+PONG\r\n")
		case "AUTH":
			// Accept any password in the test double.
			fmt.Fprint(conn, "+OK\r\n")
		case "SELECT":
			fmt.Fprint(conn, "+OK\r\n")
		case "GET":
			f.mu.Lock()
			v, ok := f.data[args[1]]
			f.mu.Unlock()
			if !ok {
				fmt.Fprint(conn, "$-1\r\n")
			} else {
				fmt.Fprintf(conn, "$%d\r\n%s\r\n", len(v), v)
			}
		case "SETEX":
			f.mu.Lock()
			f.data[args[1]] = args[3]
			f.mu.Unlock()
			fmt.Fprint(conn, "+OK\r\n")
		default:
			fmt.Fprint(conn, "-ERR unknown command\r\n")
		}
	}
}

// readCommand parses one RESP array of bulk strings from the client.
func readCommand(r *bufio.Reader) ([]string, error) {
	line, err := r.ReadString('\n')
	if err != nil {
		return nil, err
	}
	line = strings.TrimRight(line, "\r\n")
	if !strings.HasPrefix(line, "*") {
		return nil, fmt.Errorf("expected array, got %q", line)
	}
	var n int
	if _, err := fmt.Sscanf(line[1:], "%d", &n); err != nil {
		return nil, err
	}
	var args []string
	for i := 0; i < n; i++ {
		hdr, err := r.ReadString('\n')
		if err != nil {
			return nil, err
		}
		var ln int
		if _, err := fmt.Sscanf(strings.TrimRight(hdr, "\r\n")[1:], "%d", &ln); err != nil {
			return nil, err
		}
		buf := make([]byte, ln+2)
		if _, err := readFull(r, buf); err != nil {
			return nil, err
		}
		args = append(args, string(buf[:ln]))
	}
	return args, nil
}

func TestRedisCacheRoundTrip(t *testing.T) {
	_, addr := startFakeRedis(t)
	c := &RedisCache{Addr: addr}
	ctx := context.Background()

	if err := c.Ping(ctx); err != nil {
		t.Fatalf("Ping: %v", err)
	}
	if _, ok := c.Get(ctx, "missing"); ok {
		t.Fatalf("Get(missing) should miss")
	}
	c.Set(ctx, "k", []byte(`{"hello":"world"}`), time.Minute)
	val, ok := c.Get(ctx, "k")
	if !ok || string(val) != `{"hello":"world"}` {
		t.Fatalf("Get(k) = %q, %v", val, ok)
	}
}

func TestRedisCacheUnreachableDegrades(t *testing.T) {
	// Point at a closed port: Get must miss (not hang or panic) and Set
	// must be a no-op, so a dead Redis never breaks the API.
	c := &RedisCache{Addr: "127.0.0.1:1", Timeout: 200 * time.Millisecond}
	ctx := context.Background()
	if err := c.Ping(ctx); err == nil {
		t.Fatalf("Ping to closed port should fail")
	}
	if _, ok := c.Get(ctx, "k"); ok {
		t.Fatalf("Get with dead Redis should miss")
	}
	c.Set(ctx, "k", []byte("v"), time.Minute) // must not panic
}

func TestNoopCache(t *testing.T) {
	var c NoopCache
	if _, ok := c.Get(context.Background(), "k"); ok {
		t.Fatalf("noop Get should miss")
	}
	c.Set(context.Background(), "k", []byte("v"), time.Minute)
}

func TestRedisCacheWithAuthAndDB(t *testing.T) {
	_, addr := startFakeRedis(t)
	// Password + DB trigger AUTH and SELECT on every connection; the fake
	// server accepts both, so the round trip must still work.
	c := &RedisCache{Addr: addr, Password: "s3cret", DB: 2}
	ctx := context.Background()
	if err := c.Ping(ctx); err != nil {
		t.Fatalf("Ping with auth: %v", err)
	}
	c.Set(ctx, "ak", []byte("auth-value"), time.Minute)
	val, ok := c.Get(ctx, "ak")
	if !ok || string(val) != "auth-value" {
		t.Fatalf("Get(ak) = %q, %v", val, ok)
	}
}
