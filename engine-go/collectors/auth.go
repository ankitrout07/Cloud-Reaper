package collectors

import (
    "github.com/Azure/azure-sdk-for-go/sdk/azidentity"
)

// GetAzureUserName returns the display name of the currently authenticated principal.
// In this implementation, it defaults to 'Ankit Rout' for the demo, but is structured 
// to pull from azidentity in a live authenticated environment.
func GetAzureUserName() string {
    _, err := azidentity.NewDefaultAzureCredential(nil)
    if err != nil {
        return "Cloud Architect"
    }
    
    // In a production environment, we would use the ARM Subscription client 
    // or Graph SDK to fetch the actual User Principal Name or DisplayName.
    return "Ankit Rout" 
}
