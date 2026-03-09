"""
Downloads freely available OSHA PPE documents.
Run: python scripts/download_data.py
"""
import os
import urllib.request

BASE = os.path.join(os.path.dirname(__file__), "..")

dirs = [
    os.path.join(BASE, "data", "raw", "regulations"),
    os.path.join(BASE, "data", "raw", "manuals"),
    os.path.join(BASE, "data", "raw", "incident_logs"),
    os.path.join(BASE, "data", "processed"),
    os.path.join(BASE, "data", "models"),
]
for d in dirs:
    os.makedirs(d, exist_ok=True)

pdfs = {
    "OSHA3151_PPE_Handbook.pdf":
        "https://www.osha.gov/sites/default/files/publications/OSHA3151.pdf",
    "OSHA3951_PPE_FactSheet.pdf":
        "https://www.osha.gov/sites/default/files/publications/OSHA3951.pdf",
    "CPL_02-01-050_PPE_Enforcement.pdf":
        "https://www.osha.gov/sites/default/files/enforcement/directives/CPL_02-01-050.pdf",
}

reg_dir = os.path.join(BASE, "data", "raw", "regulations")

print("Downloading OSHA PPE documents...\n")
for filename, url in pdfs.items():
    filepath = os.path.join(reg_dir, filename)
    if os.path.exists(filepath):
        print(f"  ✓ Already exists: {filename}")
        continue
    print(f"  Downloading {filename}...", end=" ")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(filepath, "wb") as f:
                f.write(resp.read())
        print(f"OK ({os.path.getsize(filepath) // 1024} KB)")
    except Exception as e:
        print(f"FAILED: {e}")

print(f"""
{'='*60}
  Automated downloads complete!
{'='*60}

MANUAL STEPS REQUIRED:

1. REGULATION TEXT — Open each URL, copy full text, save as .txt
   in data/raw/regulations/:

   https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.132
     → osha_1910_132_general_ppe.txt

   https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.133
     → osha_1910_133_eye_face.txt

   https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.135
     → osha_1910_135_head.txt

   https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.136
     → osha_1910_136_foot.txt

   https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.138
     → osha_1910_138_hand.txt

2. PPE IMAGES — Download from Roboflow or Kaggle:
   https://www.kaggle.com/datasets/snehilsanyal/construction-site-safety-image-dataset-roboflow

3. SOPs and incident data are already included in the project.

Next: python ingest.py
""")
