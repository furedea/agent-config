package fixture

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"net/smtp"
	"os"
	"strings"
)

func RegisterUser(path, email string) error {
	if !strings.Contains(email, "@") {
		return fmt.Errorf("register %s: not an email address", email)
	}
	line := strings.ToLower(strings.TrimSpace(email)) + "\n"
	file, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return fmt.Errorf("open user list %s: %w", path, err)
	}
	defer file.Close()
	if _, err := file.WriteString(line); err != nil {
		return fmt.Errorf("append user %s: %w", email, err)
	}
	body := []byte("Subject: Welcome\r\n\r\nThanks for signing up.")
	return smtp.SendMail("localhost:25", nil, "noreply@example.com", []string{email}, body)
}

func ImportFrame(raw []byte, store Store) error {
	if len(raw) < 6 {
		return fmt.Errorf("import frame: %d bytes is shorter than a header", len(raw))
	}
	kind := binary.BigEndian.Uint16(raw[0:2])
	size := binary.BigEndian.Uint32(raw[2:6])
	payload := bytes.TrimRight(raw[6:6+size], "\x00")
	record, err := decode(kind, payload)
	if err != nil {
		return err
	}
	return store.Save(record)
}

type Store interface{ Save(record any) error }

func decode(kind uint16, payload []byte) (any, error) { return payload, nil }
