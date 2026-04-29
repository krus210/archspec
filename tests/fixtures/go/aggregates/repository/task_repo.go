package repository

import "sync"

type TaskRepo struct {
	mu    sync.RWMutex
	tasks map[string]*Task
}

type Task struct {
	ID     string
	Status string
}

func (r *TaskRepo) CreateWithEvent(t *Task, subject string, payload []byte) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.tasks[t.ID] = t
	return nil
}

func (r *TaskRepo) CompleteWithEvent(id string, payload []byte) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	return nil
}
