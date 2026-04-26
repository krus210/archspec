package main

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

type ServiceMap struct {
	Service struct {
		Name     string `yaml:"name"`
		Language string `yaml:"language"`
	} `yaml:"service"`
	API struct {
		Endpoints []Endpoint `yaml:"endpoints"`
	} `yaml:"api"`
	Consistency struct {
		WritePath struct {
			Pattern string `yaml:"pattern"`
		} `yaml:"write_path"`
	} `yaml:"consistency"`
	Concurrency struct {
		Aggregates []Aggregate `yaml:"aggregates"`
	} `yaml:"concurrency"`
	GoExtensions struct {
		OptimisticLockingField string `yaml:"optimistic_locking_field"`
		OutboxTable            string `yaml:"outbox_table"`
	} `yaml:"go_extensions"`
	Path string `yaml:"-"`
}

type Endpoint struct {
	Name        string      `yaml:"name"`
	Protocol    string      `yaml:"protocol"`
	Idempotency Idempotency `yaml:"idempotency"`
}

type Idempotency struct {
	Required  bool   `yaml:"required"`
	KeySource string `yaml:"key_source"`
	Storage   string `yaml:"storage"`
}

type Aggregate struct {
	Name          string `yaml:"name"`
	WriteStrategy string `yaml:"write_strategy"`
}

func LoadServiceMap(path string) (*ServiceMap, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}
	var sm ServiceMap
	if err := yaml.Unmarshal(data, &sm); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	sm.Path = path
	return &sm, nil
}
