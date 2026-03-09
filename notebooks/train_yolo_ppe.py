# ============================================================
# SafetyBuddy — YOLO26 PPE Detection Training
# ============================================================
# Run this in Google Colab with T4 GPU (free tier).
# Copy each section into a separate Colab cell.
#
# Dataset: Construction Site Safety (Kaggle)
# https://www.kaggle.com/datasets/snehilsanyal/construction-site-safety-image-dataset-roboflow
# Download the ZIP and upload to Colab before running.
# ============================================================

# ── CELL 1: Install ──
# !pip install "ultralytics>=8.4.0" -q

# ── CELL 2: Extract dataset ──
# Upload the ZIP file to Colab first, then:
# !unzip -q /content/construction-site-safety-image-dataset-roboflow.zip -d /content/dataset
#
# Alternative: Mount Google Drive if dataset is stored there
# from google.colab import drive
# drive.mount('/content/drive')
# !unzip -q "/content/drive/MyDrive/ppe_dataset.zip" -d /content/dataset

# ── CELL 3: Create data config ──
data_yaml = """
path: /content/dataset
train: train/images
val: valid/images
test: test/images

nc: 10
names:
  0: Hardhat
  1: Mask
  2: NO-Hardhat
  3: NO-Mask
  4: NO-Safety Vest
  5: Person
  6: Safety Cone
  7: Safety Vest
  8: machinery
  9: vehicle
"""

with open("/content/ppe_data.yaml", "w") as f:
    f.write(data_yaml)
print("Data config created.")

# ── CELL 4: Train YOLO26-nano ──
from ultralytics import YOLO

model = YOLO("yolo26n.pt")  # Auto-downloads YOLO26 nano weights

results = model.train(
    data="/content/ppe_data.yaml",
    epochs=50,
    imgsz=640,
    batch=16,
    device=0,              # GPU
    optimizer="auto",      # Uses MuSGD for YOLO26
    patience=10,
    lr0=0.01,
    lrf=0.01,
    mosaic=1.0,
    flipud=0.5,
    fliplr=0.5,
    project="/content/runs",
    name="ppe_yolo26n",
    plots=True,
)

print("=" * 50)
print("Training complete!")
print(f"Best weights: /content/runs/ppe_yolo26n/weights/best.pt")

# ── CELL 5: Evaluate ──
model = YOLO("/content/runs/ppe_yolo26n/weights/best.pt")
metrics = model.val(data="/content/ppe_data.yaml")

print(f"\nmAP50:      {metrics.box.map50:.4f}")
print(f"mAP50-95:   {metrics.box.map:.4f}")
print(f"Precision:  {metrics.box.mp:.4f}")
print(f"Recall:     {metrics.box.mr:.4f}")

# ── CELL 6: Test predictions ──
from IPython.display import Image, display
import glob

results = model.predict(
    source="/content/dataset/test/images",
    save=True, conf=0.4,
    project="/content/runs", name="ppe_predictions",
)

for img in sorted(glob.glob("/content/runs/ppe_predictions/*.jpg"))[:5]:
    display(Image(filename=img, width=600))

# ── CELL 7: Benchmark speed ──
import time, numpy as np

dummy = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
for _ in range(5):
    model.predict(dummy, verbose=False)

start = time.time()
for _ in range(50):
    model.predict(dummy, verbose=False)
gpu_fps = 50 / (time.time() - start)

print(f"GPU FPS: {gpu_fps:.1f}")

# ── CELL 8: Download weights ──
from google.colab import files
files.download("/content/runs/ppe_yolo26n/weights/best.pt")
print("Save as: data/models/ppe_yolo26n.pt")
