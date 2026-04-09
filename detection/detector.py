import cv2
import numpy as np
import mediapipe as mp
from scipy.spatial import distance as dist
import base64

# MediaPipe FaceMesh eye & mouth landmark indices
LEFT_EYE  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
LEFT_IRIS  = [468, 469, 470, 471, 472]
RIGHT_IRIS = [473, 474, 475, 476, 477]
MOUTH_TOP    = 13
MOUTH_BOTTOM = 14
MOUTH_LEFT   = 78
MOUTH_RIGHT  = 308

EAR_THRESHOLD   = 0.25
MAR_THRESHOLD   = 0.65
CONSEC_FRAMES   = 20

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

def _eye_aspect_ratio(landmarks, indices, w, h):
    pts = np.array([[landmarks[i].x * w, landmarks[i].y * h] for i in indices])
    A = dist.euclidean(pts[1], pts[5])
    B = dist.euclidean(pts[2], pts[4])
    C = dist.euclidean(pts[0], pts[3])
    return (A + B) / (2.0 * C)

def _mouth_aspect_ratio(landmarks, w, h):
    top    = np.array([landmarks[MOUTH_TOP].x    * w, landmarks[MOUTH_TOP].y    * h])
    bottom = np.array([landmarks[MOUTH_BOTTOM].x * w, landmarks[MOUTH_BOTTOM].y * h])
    left   = np.array([landmarks[MOUTH_LEFT].x   * w, landmarks[MOUTH_LEFT].y   * h])
    right  = np.array([landmarks[MOUTH_RIGHT].x  * w, landmarks[MOUTH_RIGHT].y  * h])
    return dist.euclidean(top, bottom) / dist.euclidean(left, right)

def process_frame(b64_image, frame_counter):
    """
    Process a base64-encoded JPEG frame.
    Returns dict: ear, mar, drowsy, yawning, face_detected, frame_count
    """
    try:
        img_bytes = base64.b64decode(b64_image.split(',')[-1])
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return _no_face(frame_counter)

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        if not results.multi_face_landmarks:
            return _no_face(frame_counter)

        lm = results.multi_face_landmarks[0].landmark

        ear_l = _eye_aspect_ratio(lm, LEFT_EYE,  w, h)
        ear_r = _eye_aspect_ratio(lm, RIGHT_EYE, w, h)
        ear   = (ear_l + ear_r) / 2.0
        mar   = _mouth_aspect_ratio(lm, w, h)

        if ear < EAR_THRESHOLD:
            frame_counter += 1
        else:
            frame_counter = max(0, frame_counter - 2)

        drowsy  = frame_counter >= CONSEC_FRAMES
        yawning = mar > MAR_THRESHOLD

        return {
            "face_detected": True,
            "ear": round(ear, 4),
            "mar": round(mar, 4),
            "ear_left":  round(ear_l, 4),
            "ear_right": round(ear_r, 4),
            "frame_counter": frame_counter,
            "drowsy":  drowsy,
            "yawning": yawning,
            "status": "DROWSY" if drowsy else ("YAWNING" if yawning else "ALERT"),
        }

    except Exception as e:
        return _no_face(frame_counter)

def _no_face(fc):
    return {
        "face_detected": False,
        "ear": 0.0, "mar": 0.0,
        "ear_left": 0.0, "ear_right": 0.0,
        "frame_counter": fc,
        "drowsy": False, "yawning": False,
        "status": "NO FACE",
    }
