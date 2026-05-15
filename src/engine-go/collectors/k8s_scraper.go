package collectors

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"

	"cloud-reaper/engine-go/models"
)

// K8sScraper implements CloudProvider for Kubernetes clusters (nodes as billable units).
type K8sScraper struct {
	creds     map[string]string
	clientset kubernetes.Interface
}

func (s *K8sScraper) Authenticate(creds map[string]string) error {
	s.creds = creds
	kubeconfig := firstNonEmpty(creds, "kubeconfig", "KUBECONFIG")
	contextName := creds["context"]

	var cfg *rest.Config
	var err error

	switch {
	case kubeconfig != "":
		var path string
		path, err = expandHome(kubeconfig)
		if err != nil {
			return fmt.Errorf("k8s: kubeconfig path: %w", err)
		}
		loading := clientcmd.NewDefaultClientConfigLoadingRules()
		loading.ExplicitPath = path
		overrides := &clientcmd.ConfigOverrides{}
		if contextName != "" {
			overrides.CurrentContext = contextName
		}
		cfg, err = clientcmd.NewNonInteractiveDeferredLoadingClientConfig(loading, overrides).ClientConfig()
	default:
		cfg, err = rest.InClusterConfig()
	}
	if err != nil {
		return fmt.Errorf("k8s: authenticate: %w", err)
	}

	cs, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		return fmt.Errorf("k8s: build client: %w", err)
	}
	s.clientset = cs
	return nil
}

func (s *K8sScraper) ScanResources() ([]models.Resource, error) {
	if s.clientset == nil {
		return nil, fmt.Errorf("k8s: not authenticated")
	}

	ctx := context.Background()
	nodes, err := s.clientset.CoreV1().Nodes().List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, fmt.Errorf("k8s: list nodes: %w", err)
	}

	now := time.Now().UTC()
	var resources []models.Resource
	for _, node := range nodes.Items {
		resources = append(resources, nodeToResource(node, now))
	}

	pods, err := s.clientset.CoreV1().Pods("").List(ctx, metav1.ListOptions{
		FieldSelector: "status.phase=Failed",
	})
	if err == nil {
		for _, pod := range pods.Items {
			if pod.DeletionTimestamp != nil {
				continue
			}
			resources = append(resources, models.Resource{
				ID:            string(pod.UID),
				Name:          fmt.Sprintf("%s/%s", pod.Namespace, pod.Name),
				Type:          "FailedPod",
				Region:        "cluster",
				Tags:          podLabelsToMap(pod.Labels),
				Active:        true,
				IsProtected:   false,
				IsUnallocated: true,
				LastSeen:      now,
				Provider:      "k8s",
				SKU:           "pod",
			})
		}
	}

	return resources, nil
}

func (s *K8sScraper) GetHourlyRate(sku string) (float64, error) {
	rates := map[string]float64{
		"node":            0.05,
		"pod":             0.001,
		"Standard_D2s_v3": 0.096,
	}
	if rate, ok := rates[sku]; ok {
		return rate, nil
	}
	return 0, fmt.Errorf("k8s: hourly rate not found for sku %q", sku)
}

func nodeToResource(node corev1.Node, seen time.Time) models.Resource {
	tags := podLabelsToMap(node.Labels)
	instanceType := node.Labels["node.kubernetes.io/instance-type"]
	if instanceType == "" {
		instanceType = node.Labels["beta.kubernetes.io/instance-type"]
	}
	if instanceType == "" {
		instanceType = "node"
	}

	cpuCap := node.Status.Capacity.Cpu().AsApproximateFloat64()
	cpuAlloc := node.Status.Allocatable.Cpu().AsApproximateFloat64()
	util := 0.0
	if cpuCap > 0 {
		util = cpuAlloc / cpuCap
	}

	return models.Resource{
		ID:            string(node.UID),
		Name:          node.Name,
		Type:          "KubernetesNode",
		Region:        "cluster",
		Tags:          tags,
		Active:        isNodeReady(node),
		IsProtected:   isK8sProtected(tags),
		IsUnallocated: util < 0.20,
		LastSeen:      seen,
		Provider:      "k8s",
		SKU:           instanceType,
	}
}

func isNodeReady(node corev1.Node) bool {
	for _, c := range node.Status.Conditions {
		if c.Type == corev1.NodeReady {
			return c.Status == corev1.ConditionTrue
		}
	}
	return false
}

func isK8sProtected(tags map[string]string) bool {
	for k, v := range tags {
		key := strings.ToLower(k)
		val := strings.ToLower(v)
		if (key == KeyReaperIgnore && val == ValueTrue) || (key == KeyEnvironment && val == ValueProduction) {
			return true
		}
	}
	return false
}

func podLabelsToMap(labels map[string]string) map[string]string {
	if labels == nil {
		return map[string]string{}
	}
	out := make(map[string]string, len(labels))
	for k, v := range labels {
		out[k] = v
	}
	return out
}

func expandHome(path string) (string, error) {
	if strings.HasPrefix(path, "~/") {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		return filepath.Join(home, path[2:]), nil
	}
	return path, nil
}
