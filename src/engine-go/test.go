package main
import (
	"fmt"
	"time"
)
func main() {
	start := time.Now().Add(-7 * 24 * time.Hour)
	end := time.Now()
	timespan := fmt.Sprintf("%s/%s", start.Format(time.RFC3339), end.Format(time.RFC3339))
	fmt.Println(timespan)
}
