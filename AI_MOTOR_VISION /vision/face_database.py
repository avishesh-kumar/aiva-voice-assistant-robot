import json
import os
import cv2

import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime


class FaceDatabase:
    """
    Face embedding database using cosine similarity.

    Stores multiple embeddings per person to improve robustness.
    """

    def __init__(
        self,
        db_path: str = "memory/faces/face_memory.json",
        similarity_threshold: float = 0.52,
    ):
        self.db_path = db_path
        self.similarity_threshold = similarity_threshold

        self.db: Dict[str, Dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def match(self, embedding: np.ndarray):
        scores = []

        for name, data in self.db.items():
            for stored in data.get("embeddings", []):
                stored_vec = np.array(stored, dtype=np.float32)
                score = self._cosine_similarity(embedding, stored_vec)
                scores.append((name, score))

        if not scores:
            return "Unknown", 0.0

        # Sort best matches
        scores.sort(key=lambda x: x[1], reverse=True)
        best_name, best_score = scores[0]

        # Allow weaker match if seen before
        if best_score >= self.similarity_threshold:
            return best_name, best_score

        # 🔥 SECOND CHANCE: soft match if multiple embeddings exist
        matches = [s for s in scores if s[0] == best_name and s[1] > 0.48]

        if len(matches) >= 2:
            return best_name, best_score

        return "Unknown", best_score

    def add_face(
        self,
        name: str,
        embedding: np.ndarray,
    ):
        """
        Add a new face embedding to the database.
        """
        if name not in self.db:
            self.db[name] = {
                "embeddings": [],
                "times_seen": 0,
                "last_seen": None,
            }

        self.db[name]["embeddings"].append(embedding.tolist())
        self.db[name]["times_seen"] += 1
        self.db[name]["last_seen"] = datetime.utcnow().isoformat()

        #self._save()

    def update_seen(self, name: str):
        """
        Update metadata when a known face is seen again.
        """
        if name not in self.db:
            return

        self.db[name]["times_seen"] += 1
        self.db[name]["last_seen"] = datetime.utcnow().isoformat()
        #self._save()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cosine_similarity(
        self,
        a: np.ndarray,
        b: np.ndarray,
    ) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def _load(self):
        
        return

    '''def _save(self):
        with open(self.db_path, "w") as f:
            json.dump(self.db, f, indent=2)'''

    def reload(self):
        """Reload face database from disk."""
        return

    def load_from_photo_folders(
        self,
        base_dir: str,
        detector,
        recognizer,
    ):
        """
        Load face embeddings from folders:
        base_dir/
          PersonName/
            img1.jpg
            img2.jpg
        """
        self.db = {}  # 🔒 RESET, read-only DB

        if not os.path.exists(base_dir):
            print(f"[FACE_DB] Folder not found: {base_dir}")
            return

        for person in os.listdir(base_dir):
            person_dir = os.path.join(base_dir, person)
            if not os.path.isdir(person_dir):
                continue

            valid_embeddings = []

            for fname in os.listdir(person_dir):
                if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue

                path = os.path.join(person_dir, fname)
                img = cv2.imread(path)
                if img is None:
                    print(f"[FACE_DB] Skipped unreadable image: {path}")
                    continue

                boxes = detector.detect_faces(img)

                # STRICT mode + SKIP
                if len(boxes) != 1:
                    print(f"[FACE_DB] Skipped {path} (faces={len(boxes)})")
                    continue

                emb = recognizer.extract_embedding(img, boxes[0])
                if emb is None:
                    print(f"[FACE_DB] Failed embedding: {path}")
                    continue

                valid_embeddings.append(emb.tolist())

            if valid_embeddings:
                self.db[person] = {
                    "embeddings": valid_embeddings,
                    "times_seen": 0,
                    "last_seen": None,
                }
                print(f"[FACE_DB] Loaded {len(valid_embeddings)} photos for {person}")
            else:
                print(f"[FACE_DB] No valid photos for {person}")



