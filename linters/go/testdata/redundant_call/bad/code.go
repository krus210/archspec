package svc

type GeoClient interface {
	GetDistance(a, b string) float64
	GetDistancesBatch(pairs [][2]string) []float64
}

func rank(c GeoClient, workers []string) []float64 {
	dists := make([]float64, 0, len(workers))
	for _, w := range workers {
		d := c.GetDistance(w, "task-city")
		dists = append(dists, d)
	}
	return dists
}
