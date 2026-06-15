package collectors

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
)

type AzurePriceResult struct {
	Items []map[string]interface{} `json:"Items"`
}

func FetchAzurePrice(sku string, region string) (float64, error) {
	filter := fmt.Sprintf("armSkuName eq '%s' and priceType eq 'Consumption'", sku)
	if region != "" {
		filter = fmt.Sprintf("%s and armRegionName eq '%s'", filter, region)
	}
	baseURL := fmt.Sprintf("https://prices.azure.com/api/retail/prices?currencyCode=USD&$filter=%s", url.QueryEscape(filter))

	resp, err := http.Get(baseURL)
	if err != nil {
		return 0, err
	}
	defer func() {
		_ = resp.Body.Close()
	}()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return 0, err
	}

	var result AzurePriceResult
	if err := json.Unmarshal(body, &result); err != nil {
		return 0, err
	}

	if len(result.Items) > 0 {
		if price, ok := result.Items[0]["retailPrice"].(float64); ok {
			return price, nil
		}
	}

	return 0, fmt.Errorf("price not found for sku %s in region %s", sku, region)
}

func FetchAWSPrice(sku string, region string) (float64, error) {
	// AWS Price List API is complex, using a simplified heuristic for now
	// but the intention is to move away from hardcoded maps in the scraper.
	// Real implementation would use the AWS Price List Query API.
	return 0.1, nil
}
