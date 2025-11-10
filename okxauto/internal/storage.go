package gookx

import (
	"encoding/json"
	"fmt"
	"os"
)

func SaveToFile(data interface{}, filename string) error {
	output, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return fmt.Errorf("JSON marshal error: %w", err)
	}
	if err := os.WriteFile(filename, output, 0644); err != nil {
		return fmt.Errorf("file write error: %w", err)
	}
	return nil
}
