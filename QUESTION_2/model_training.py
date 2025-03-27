# -*- coding: utf-8 -*-
"""model_training.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/12cemP8WuJnUN5bk0bRrBeWRZy_tjAeYv
"""

import os
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns

# ----------------------------------------------------
#               Mount Google Drive (for Data)
# ----------------------------------------------------
from google.colab import drive
drive.mount('/content/drive')

# ----------------------------------------------------
#                   Paths & Setup
# ----------------------------------------------------
MFCC_DIR = "/content/mfcc_feature"
SAVE_DIR = "/content"
CONF_MAT_DIR = os.path.join(SAVE_DIR, "confusion_matrices")

os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(CONF_MAT_DIR, exist_ok=True)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# ----------------------------------------------------
#                   Data Loading
# ----------------------------------------------------
X, y = [], []
label_map = {}

# Loop through each language folder and load MFCC features
for idx, language in enumerate(sorted(os.listdir(MFCC_DIR))):
    language_path = os.path.join(MFCC_DIR, language)
    if os.path.isdir(language_path):
        label_map[idx] = language
        for file in os.listdir(language_path):
            if file.endswith('.npy'):
                mfcc = np.load(os.path.join(language_path, file))
                X.append(mfcc.flatten())
                y.append(idx)

X, y = np.array(X), np.array(y)

# ----------------------------------------------------
#      Train / Validation Split (80/20)
# ----------------------------------------------------
X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
print(f"Training samples: {len(X_train)}")
print(f"Validation samples: {len(X_val)}")

# ----------------------------------------------------
#                 Data Normalization
# ----------------------------------------------------
scaler = StandardScaler()
X_train = scaler.fit_transform(X_train)
X_val = scaler.transform(X_val)

# ----------------------------------------------------
#             Create Datasets & Dataloaders
# ----------------------------------------------------
def create_dataloader(X, y, batch_size=64):
    X_tensor = torch.tensor(X, dtype=torch.float32)
    y_tensor = torch.tensor(y, dtype=torch.long)
    dataset = TensorDataset(X_tensor, y_tensor)
    return DataLoader(dataset, batch_size=batch_size, shuffle=True)

train_loader = create_dataloader(X_train, y_train, batch_size=64)
val_loader = create_dataloader(X_val, y_val, batch_size=64)

#----------------------------------------------------
#               Define the MLP Model
# ----------------------------------------------------
class MLP(nn.Module):
    def __init__(self, input_dim, num_classes):
        super(MLP, self).__init__()
        self.classifier = nn.Sequential(
            nn.Linear(input_dim, 1024), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(1024, 512), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(64, num_classes)
        )

    def forward(self, x):
        return self.classifier(x)

# ----------------------------------------------------
#    Helper: Evaluate Model & Get Metrics
# ----------------------------------------------------
def evaluate_model(model, data_loader, criterion):
    model.eval()
    total_loss = 0
    y_true, y_pred = [], []
    with torch.no_grad():
        for inputs, labels in data_loader:
            inputs, labels = inputs.to(device), labels.to(device)
            outputs = model(inputs)
            total_loss += criterion(outputs, labels).item()
            _, predicted = torch.max(outputs, 1)
            y_pred.extend(predicted.cpu().numpy())
            y_true.extend(labels.cpu().numpy())
    avg_loss = total_loss / len(data_loader)
    accuracy = accuracy_score(y_true, y_pred)
    return avg_loss, accuracy, y_true, y_pred

# ----------------------------------------------------
#    Helper: Plot & Save Confusion Matrix
# ----------------------------------------------------
def plot_confusion_matrix(y_true, y_pred, label_map, epoch, save_path):
    labels_order = sorted(label_map.keys())
    cm = confusion_matrix(y_true, y_pred, labels=labels_order)
    plt.figure(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=[label_map[k] for k in labels_order],
                yticklabels=[label_map[k] for k in labels_order])
    plt.title(f'Confusion Matrix - Epoch {epoch+1}')
    plt.xlabel('Predicted')
    plt.ylabel('Actual')
    plt.savefig(save_path, dpi=300)
    plt.close()

# ----------------------------------------------------
#               Instantiate Model, Loss & Optimizer
# ----------------------------------------------------
input_dim = X_train.shape[1]
num_classes = len(label_map)
model = MLP(input_dim=input_dim, num_classes=num_classes).to(device)
criterion = nn.CrossEntropyLoss()
optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
# ----------------------------------------------------
#              Training Loop
# ----------------------------------------------------
num_epochs = 20
best_val_acc = 0

for epoch in range(num_epochs):
    model.train()
    running_loss = 0
    train_y_true, train_y_pred = [], []

    for inputs, labels in train_loader:
        inputs, labels = inputs.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        running_loss += loss.item()

        _, predicted = torch.max(outputs, 1)
        train_y_pred.extend(predicted.cpu().numpy())
        train_y_true.extend(labels.cpu().numpy())

    train_loss = running_loss / len(train_loader)
    train_acc = accuracy_score(train_y_true, train_y_pred) * 100  # Convert to percentage
    val_loss, val_acc, val_y_true, val_y_pred = evaluate_model(model, val_loader, criterion)
    val_acc *= 100  # Convert to percentage

    # Save the best model based on validation accuracy
    if val_acc > best_val_acc:
        best_val_acc = val_acc
        torch.save(model.state_dict(), os.path.join(SAVE_DIR, "best_model.pt"))

    print(f"Epoch {epoch+1}: Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.2f}%, "
          f"Val Loss: {val_loss:.4f}, Val Acc: {val_acc:.2f}%")

# ----------------------------------------------------
#   Load Best Model & Evaluate on Validation Set
# ----------------------------------------------------
model.load_state_dict(torch.load(os.path.join(SAVE_DIR, "best_model.pt")))
val_loss, val_acc, val_y_true, val_y_pred = evaluate_model(model, val_loader, criterion)
val_acc *= 100  # Convert to percentage

print(f"✅ Final Validation Loss: {val_loss:.4f}")
print(f"✅ Final Validation Accuracy: {val_acc:.2f}%")
print(classification_report(val_y_true, val_y_pred, target_names=[label_map[k] for k in sorted(label_map.keys())]))

# Save final confusion matrix for the validation set
conf_mat_path = os.path.join(SAVE_DIR, "final_confusion_matrix.png")
plot_confusion_matrix(val_y_true, val_y_pred, label_map, num_epochs, conf_mat_path)
print(f"Confusion matrix saved to {conf_mat_path}")