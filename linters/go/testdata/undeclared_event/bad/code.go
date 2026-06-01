package svc

const (
	subjectTaskFailed = "task.failed"
	subjectUnknown    = "task.unknown"
)

type Conn interface {
	Publish(subj string, data []byte) error
	Subscribe(subj string, cb func()) error
}

func emit(nc Conn) {
	nc.Publish(subjectTaskFailed, []byte("{}"))
	nc.Subscribe(subjectUnknown, nil)
}
