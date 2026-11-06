package cache

import "testing"

func TestParseRedisURL(t *testing.T) {
	cases := []struct {
		in       string
		addr     string
		password string
		db       int
		wantErr  bool
	}{
		{"redis://localhost:6379", "localhost:6379", "", 0, false},
		{"redis://localhost", "localhost:6379", "", 0, false},
		{"redis://:s3cret@redis.example.com:6380/2", "redis.example.com:6380", "s3cret", 2, false},
		{"redis://user:pass@127.0.0.1:6379/0", "127.0.0.1:6379", "pass", 0, false},
		{"localhost:6379", "localhost:6379", "", 0, false},
		{"rediss://localhost:6379", "", "", 0, true},
		{"http://localhost:6379", "", "", 0, true},
		{"redis://localhost:6379/notanumber", "", "", 0, true},
		{"", "", "", 0, true},
	}
	for _, tc := range cases {
		addr, pw, db, err := ParseRedisURL(tc.in)
		if tc.wantErr {
			if err == nil {
				t.Errorf("ParseRedisURL(%q) = no error, want error", tc.in)
			}
			continue
		}
		if err != nil {
			t.Errorf("ParseRedisURL(%q) error: %v", tc.in, err)
			continue
		}
		if addr != tc.addr || pw != tc.password || db != tc.db {
			t.Errorf("ParseRedisURL(%q) = (%q, %q, %d), want (%q, %q, %d)",
				tc.in, addr, pw, db, tc.addr, tc.password, tc.db)
		}
	}
}
