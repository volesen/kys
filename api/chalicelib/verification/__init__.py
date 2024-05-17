import os

import boto3
from chalice import Blueprint, NotFoundError
from chalicelib.models.session import SessionRepository, Session, SessionState

APP_BUCKET_NAME = os.environ["APP_BUCKET_NAME"]

bp = Blueprint(__name__)

session_respository = SessionRepository()

def compare_faces(source_object_name, target_object_name, threshold=90):
    rekognition_client = boto3.client("rekognition")

    response = rekognition_client.compare_faces(
        SourceImage={
            "S3Object": {"Bucket": APP_BUCKET_NAME, "Name": source_object_name}
        },
        TargetImage={
            "S3Object": {"Bucket": APP_BUCKET_NAME, "Name": target_object_name}
        },
    )

    return (
        len(response["FaceMatches"]) == 1
        and len(response["UnmatchedFaces"]) == 0
        and response["FaceMatches"][0]["Similarity"] > threshold
    )


def needles_in_haystack(needles, haystack):
    for needle in needles:
        for text in haystack["TextDetections"]:
            if needle in text["DetectedText"] and text["Type"] == "LINE":
                break
        else:
            return False

    return True


def image_contains_texts(object_name, texts):
    rekognition_client = boto3.client("rekognition")

    response = rekognition_client.detect_text(
        Image={
            "S3Object": {
                "Bucket": APP_BUCKET_NAME,
                "Name": object_name,
            }
        }
    )

    return needles_in_haystack(texts, response)


@bp.on_s3_event(bucket=APP_BUCKET_NAME, events=["s3:ObjectCreated:*"])
def handle_s3_event(event):
    print(f"Received S3 event: {event}")

    session_id, file = event.key.split("/")

    if file not in ["selfie", "student-id"]:
        return

    if file == "selfie":
        # Update the session state, state = selfie-submitted
        session_respository.update_session_state(session_id, "selfie-submitted")
        # get_db().update_item(
        #     Key={"id": session_id},
        #     UpdateExpression="SET #state = :state",
        #     ExpressionAttributeNames={"#state": "state"},
        #     ExpressionAttributeValues={":state": "selfie-submitted"},
        # )

    #
    # session = get_db().get_item(Key={"id": session_id})["Item"]
    session = session_respository.get_session(session_id)

    if not session:
        raise NotFoundError("Session not found.")

    selfie_object_name = f"{session_id}/selfie"
    student_id_object_name = f"{session_id}/student-id"

    # Check if text matches
    text_matches = image_contains_texts(
        student_id_object_name,
        [
            session["name"],
            session["university"],
        ],
    )

    if not text_matches:
        # Update the session state, state = text-not-matched

        # get_db().update_item(
        #     Key={"id": session_id},
        #     UpdateExpression="SET #state = :state",
        #     ExpressionAttributeNames={"#state": "state"},
        #     ExpressionAttributeValues={":state": "text-not-matched"},
        # )
        session_respository.update_session_state(session_id, "text-not-matched")
        return

    # Check if faces match

    faces_match = compare_faces(
        selfie_object_name,
        student_id_object_name,
    )

    if not faces_match:
        # Update the session state, state = faces-not-matched
        # get_db().update_item(
        #     Key={"id": session_id},
        #     UpdateExpression="SET #state = :state",
        #     ExpressionAttributeNames={"#state": "state"},
        #     ExpressionAttributeValues={":state": "faces-not-matched"},
        # )
        session_respository.update_session_state(session_id, "faces-not-matched")
        return

    # Update the session state, state = approved
    # get_db().update_item(
    #     Key={"id": session_id},
    #     UpdateExpression="SET #state = :state",
    #     ExpressionAttributeNames={"#state": "state"},
    #     ExpressionAttributeValues={":state": "approved"},
    # )
    session_respository.update_session_state(session_id, "approved")
