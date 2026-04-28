package collectors

import (
	"context"
	"github.com/microsoftgraph/msgraph-sdk-go"
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
)

// GetAzureUserName returns the display name of the currently authenticated principal
// using the Microsoft Graph API. This eliminates hardcoded values and makes the 
// Mission Briefing context-aware.
func GetAzureUserName() string {
	// 1. Use the same credential as ARM collectors
	cred, err := azidentity.NewDefaultAzureCredential(nil)
	if err != nil {
		return "Cloud Architect"
	}

	// 2. Initialize Graph Client
	client, err := msgraphsdk.NewGraphServiceClientWithCredentials(cred, []string{"https://graph.microsoft.com/.default"})
	if err != nil {
		return "Cloud Architect"
	}

	// 3. Fetch the 'Me' object (the currently signed-in user)
	// We use context.Background() here for simplicity in this synchronous call
	user, err := client.Me().Get(context.Background(), nil)
	if err != nil {
		// This often fails if the principal doesn't have Graph permissions
		// or if running in a restricted service principal context.
		return "Cloud Architect" 
	}

	// 4. Extract the Display Name
	displayName := user.GetDisplayName()
	if displayName == nil {
		return "Cloud Architect"
	}

	return *displayName
}
