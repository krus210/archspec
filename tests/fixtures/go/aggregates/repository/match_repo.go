package repository

import "sync"

type MatchRepo struct {
	mu      sync.Mutex
	matches map[string]*Match
}

type Match struct {
	ID     string
	Status string
}

func (r *MatchRepo) CreatePendingIfAbsent(taskID string) (alreadyCompleted bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	return false
}
