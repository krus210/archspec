package usecase

import "sync"

// This Mutex is OUTSIDE the aggregate scope (usecase/) and must be ignored.
type Service struct {
	mu sync.Mutex
}

func (s *Service) DoSomething() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	return nil
}
