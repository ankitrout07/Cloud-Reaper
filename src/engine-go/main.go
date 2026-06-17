//go:build !headless && !cli

package main

import "cloud-reaper/engine-go/internal/desktop"

func main() {
	desktop.Run()
}
