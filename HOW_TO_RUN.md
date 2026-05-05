# 📖 How to Run Cloud-Reaper

A simple guide to set up and run Cloud-Reaper for Azure cost optimization.

---

## 🛠 Prerequisites

Before you start, make sure you have:
- **Python 3.12+** installed
- **Go 1.24+** installed (for the pricing engine)
- **Azure CLI** installed (`az login` to authenticate)
- **PostgreSQL** running (for data storage)

---

## ⚡ Quick Start (Recommended)

### Step 1: Set Up Virtual Environment

```bash
# Create a virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate    # On Linux/macOS
# OR
venv\Scripts\activate       # On Windows
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Set Up Azure Credentials

Edit the `.env` file and add your Azure subscription ID:

```bash
# Copy the template
cp .env.example .env        # If available, or create manually

# Edit .env and add:
AZURE_SUBSCRIPTION_ID=your-subscription-id-here
AZURE_TENANT_ID=your-tenant-id
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your-token
```

Get your subscription ID:
```bash
az account list --query "[].{Name:name, ID:id}" -o table
```

### Step 4: Start PostgreSQL

```bash
# On Linux
sudo systemctl start postgresql

# Or with Docker
docker run --name cloud-reaper-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres
```

### Step 5: Run Cloud-Reaper

**Option A: CLI Mode (Resource Scanning)**
```bash
python3 main.py
```

**Option B: Dashboard Mode (Web UI)**
```bash
python3 ui/app.py
```
Then open `http://localhost:5000` in your browser.

---

## 🤖 Automated Setup (Using the Bootstrap Script)

If you prefer automated setup:

```bash
# Make the script executable
chmod +x reap.sh

# Run it (handles venv creation, dependencies, and Go build)
./reap.sh
```

The script automatically:
- ✅ Creates a virtual environment
- ✅ Installs Python dependencies
- ✅ Builds the Go performance core
- ✅ Launches the main engine

---

## 📋 Environment Variables Reference

Create a `.env` file in the project root with these values:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_SUBSCRIPTION_ID` | Yes | Your Azure subscription ID |
| `AZURE_TENANT_ID` | Optional | Azure AD tenant ID (for Service Principal auth) |
| `AZURE_CLIENT_ID` | Optional | Service Principal client ID |
| `AZURE_CLIENT_SECRET` | Optional | Service Principal secret |
| `INFLUXDB_URL` | Optional | InfluxDB endpoint (default: `http://localhost:8086`) |
| `INFLUXDB_TOKEN` | Optional | InfluxDB authentication token |
| `INFLUXDB_ORG` | Optional | InfluxDB organization name |
| `INFLUXDB_BUCKET` | Optional | InfluxDB bucket name |

---

## 🔑 Azure Authentication

### Option 1: Azure CLI (Easiest)
```bash
az login
# Cloud-Reaper will use your CLI credentials automatically
```

### Option 2: Service Principal (Enterprise)
```bash
# Create a service principal
az ad sp create-for-rbac --name "cloud-reaper" --role Reader

# Add the credentials to .env:
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
```

---

## ✅ Verify Your Setup

```bash
# Activate virtual environment
source venv/bin/activate

# Test Python dependencies
python3 -c "import azure; print('✅ Azure SDK installed')"

# Test the main script
python3 main.py
```

---

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| `No module named 'azure'` | Ensure venv is activated: `source venv/bin/activate` |
| `Invalid subscription ID` | Update `.env` with real Azure subscription ID |
| `PostgreSQL connection refused` | Start PostgreSQL: `sudo systemctl start postgresql` |
| `Go binary not found` | Run `./reap.sh` or manually: `cd engine-go && go build -o reaper-engine main.go` |

---

## 📚 Next Steps

1. Explore the **Dashboard** at `http://localhost:5000`
2. Configure **Settings** with your Azure subscription
3. Run scans to identify **cost optimization opportunities**
4. Review **reports** and take action on recommendations
