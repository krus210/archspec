package svc

const (
	subjectTaskFailed  = "task.failed"
	subjectTaskCreated = "task.created"
)

type Conn interface {
	Publish(subj string, data []byte) error
	Subscribe(subj string, cb func()) error
}

func emit(nc Conn) {
	nc.Publish(subjectTaskFailed, []byte("{}"))
	nc.Subscribe(subjectTaskCreated, nil)
}
