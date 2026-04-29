package repository

import "sync"

// Pessimistic-only aggregate: Mutex but no CAS-style methods.
type ProfileRepo struct {
	mu       sync.RWMutex
	profiles map[string]*Profile
}

type Profile struct {
	ID       string
	FullName string
}

func (r *ProfileRepo) Get(id string) *Profile {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.profiles[id]
}

func (r *ProfileRepo) Update(p *Profile) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.profiles[p.ID] = p
}
