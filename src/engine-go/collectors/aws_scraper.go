package collectors

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/ec2"
	"github.com/aws/aws-sdk-go-v2/service/ec2/types"

	"cloud-reaper/engine-go/models"
)

// AWSScraper implements CloudProvider for AWS accounts.
type AWSScraper struct {
	creds  map[string]string
	region string
	client *ec2.Client
}

func (s *AWSScraper) Authenticate(creds map[string]string) error {
	s.creds = creds
	accessKey := firstNonEmpty(creds, "access_key_id", "AWS_ACCESS_KEY_ID")
	secretKey := firstNonEmpty(creds, "secret_access_key", "AWS_SECRET_ACCESS_KEY")
	if accessKey == "" || secretKey == "" {
		return fmt.Errorf("aws: access_key_id and secret_access_key are required")
	}

	s.region = firstNonEmpty(creds, "region", "AWS_REGION")
	if s.region == "" {
		s.region = "us-east-1"
	}

	cfg, err := config.LoadDefaultConfig(context.Background(),
		config.WithRegion(s.region),
		config.WithCredentialsProvider(credentials.NewStaticCredentialsProvider(accessKey, secretKey, "")),
	)
	if err != nil {
		return fmt.Errorf("aws: authenticate: %w", err)
	}
	s.client = ec2.NewFromConfig(cfg)
	return nil
}

func (s *AWSScraper) ScanResources() ([]models.Resource, error) {
	if s.client == nil {
		return nil, fmt.Errorf("aws: not authenticated")
	}

	ctx := context.Background()
	var resources []models.Resource
	now := time.Now().UTC()

	instances, err := s.client.DescribeInstances(ctx, &ec2.DescribeInstancesInput{})
	if err != nil {
		return nil, fmt.Errorf("aws: describe instances: %w", err)
	}
	for _, reservation := range instances.Reservations {
		for _, inst := range reservation.Instances {
			if inst.InstanceId == nil {
				continue
			}
			tags := awsTagsToMap(inst.Tags)
			name := *inst.InstanceId
			if v, ok := tags["Name"]; ok {
				name = v
			}
			sku := string(inst.InstanceType)
			state := string(inst.State.Name)
			resources = append(resources, models.Resource{
				ID:            *inst.InstanceId,
				Name:          name,
				Type:          "EC2Instance",
				Region:        s.region,
				Tags:          tags,
				Active:        state == string(types.InstanceStateNameRunning),
				IsProtected:   isAWSProtected(tags),
				IsUnallocated: state == string(types.InstanceStateNameStopped),
				LastSeen:      now,
				Provider:      "aws",
				SKU:           sku,
			})
		}
	}

	volumes, err := s.client.DescribeVolumes(ctx, &ec2.DescribeVolumesInput{
		Filters: []types.Filter{{
			Name:   aws.String("status"),
			Values: []string{"available"},
		}},
	})
	if err != nil {
		return resources, fmt.Errorf("aws: describe volumes: %w", err)
	}
	for _, vol := range volumes.Volumes {
		if vol.VolumeId == nil {
			continue
		}
		tags := awsTagsToMap(vol.Tags)
		resources = append(resources, models.Resource{
			ID:            *vol.VolumeId,
			Name:          *vol.VolumeId,
			Type:          "OrphanedEBSVolume",
			Region:        s.region,
			Tags:          tags,
			Active:        true,
			IsProtected:   isAWSProtected(tags),
			IsUnallocated: true,
			LastSeen:      now,
			Provider:      "aws",
			SKU:           string(vol.VolumeType),
		})
	}

	return resources, nil
}

func (s *AWSScraper) GetHourlyRate(sku string) (float64, error) {
	rates := map[string]float64{
		"t3.micro":  0.0104,
		"t3.small":  0.0208,
		"m5.large":  0.096,
		"m5.xlarge": 0.192,
		"gp3":       0.00008, // per GB-hour approximation
	}
	if rate, ok := rates[sku]; ok {
		return rate, nil
	}
	return 0, fmt.Errorf("aws: hourly rate not found for sku %q", sku)
}

func awsTagsToMap(tags []types.Tag) map[string]string {
	out := make(map[string]string, len(tags))
	for _, t := range tags {
		if t.Key != nil && t.Value != nil {
			out[*t.Key] = *t.Value
		}
	}
	return out
}

func isAWSProtected(tags map[string]string) bool {
	for k, v := range tags {
		key := strings.ToLower(k)
		val := strings.ToLower(v)
		if (key == KeyReaperIgnore && val == ValueTrue) || (key == KeyEnvironment && val == ValueProduction) {
			return true
		}
	}
	return false
}

func firstNonEmpty(m map[string]string, keys ...string) string {
	for _, k := range keys {
		if v := strings.TrimSpace(m[k]); v != "" {
			return v
		}
	}
	return ""
}
