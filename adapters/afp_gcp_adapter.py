import os
from google.cloud import run_v2
from opentelemetry import metrics
from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

class GCPForgeAdapter:
    def __init__(self, project_id, location, service_name):
        self.project_id = project_id
        self.location = location
        self.service_name = service_name
        # Initialize the Cloud Run client
        self.run_client = run_v2.ServicesClient()
        self._setup_telemetry()

    def _setup_telemetry(self):
        """
        Sets up OpenTelemetry to export custom metrics (like Causal Emergence and Shannon Entropy)
        directly to Google Cloud Monitoring.
        """
        try:
            # Create the Cloud Monitoring exporter
            exporter = CloudMonitoringMetricsExporter(
                project_id=self.project_id
            )
            # Create a reader that periodically exports metrics
            reader = PeriodicExportingMetricReader(exporter, export_interval_millis=10000)
            
            # Setup the MeterProvider with the exporter
            provider = MeterProvider(metric_readers=[reader])
            metrics.set_meter_provider(provider)
            
            self.meter = metrics.get_meter("forge.cognitive.metrics")
            
            # Create specific instruments for our metrics
            self.entropy_recorder = self.meter.create_histogram(
                "forge.shannon_entropy",
                description="Records the Shannon Entropy degradation of the cognitive model",
                unit="1"
            )
            
            self.causal_emergence_recorder = self.meter.create_histogram(
                "forge.causal_emergence_score",
                description="Records the Causal Emergence Score of the cognitive model",
                unit="1"
            )
        except Exception as e:
            print(f"[-] Telemetry setup failed: {e}")

    def spawn_isolated_instance(self, image_uri):
        """
        Spawns a completely isolated, containerized instance of the cognitive model
        on Google Cloud Run to ensure a clean slate for perturbation tests.
        """
        parent = f"projects/{self.project_id}/locations/{self.location}"
        
        # Define the new service (isolated cognitive instance)
        service = run_v2.Service()
        service.template.containers = [
            run_v2.Container(image=image_uri)
        ]
        
        request = run_v2.CreateServiceRequest(
            parent=parent,
            service=service,
            service_id=self.service_name,
        )
        
        print(f"[*] Spawning isolated instance '{self.service_name}' in {self.location}...")
        try:
            operation = self.run_client.create_service(request=request)
            response = operation.result()
            print(f"[+] Isolated instance spawned successfully: {response.uri}")
            return response.uri
        except Exception as e:
            print(f"[-] Failed to spawn instance: {e}")
            return None

    def record_entropy_metric(self, value):
        """Logs the Shannon Entropy score to GCP."""
        print(f"[*] Recording Shannon Entropy: {value}")
        if hasattr(self, 'entropy_recorder'):
            self.entropy_recorder.record(value)

    def record_causal_emergence(self, value):
        """Logs the Causal Emergence Score to GCP."""
        print(f"[*] Recording Causal Emergence Score: {value}")
        if hasattr(self, 'causal_emergence_recorder'):
            self.causal_emergence_recorder.record(value)

# ==========================================
# 🛑 SYSTEM SELF-CHECK & CONFIGURATION MAP
# ==========================================
def run_self_check():
    """
    Validates the environment and provides the user with the exact 
    variables and URLs needed for the adapter to function.
    """
    missing_configs = []
    
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        missing_configs.append("GCP_PROJECT_ID")
        
    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials:
        missing_configs.append("GOOGLE_APPLICATION_CREDENTIALS")

    print("\n[🛠️ FORGE ADAPTER SELF-CHECK 🛠️]")
    if not missing_configs:
        print("[+] System Check Passed. All critical environment variables detected.")
    else:
        print("[-] System Check Failed. Missing required configurations.")
        print("\n--- REQUIRED PLUG-INS ---")
        print("1. GCP Project ID:")
        print("   -> Where: Set environment variable 'GCP_PROJECT_ID'")
        print("   -> What: Your Google Cloud Project ID (e.g., 'drift-forge-production-123')")
        print("2. Google Credentials:")
        print("   -> Where: Set environment variable 'GOOGLE_APPLICATION_CREDENTIALS'")
        print("   -> What: Absolute path to your service account JSON key (e.g., '/home/crexs/keys/gcp-key.json')")
        print("\nEnsure the Google Cloud Run API and Cloud Monitoring API are enabled in your GCP Console.")

if __name__ == "__main__":
    run_self_check()
