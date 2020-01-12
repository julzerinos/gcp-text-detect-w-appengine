import os
import io

from google.cloud import storage
from google.cloud import pubsub_v1
from google.cloud import vision
from google.cloud import datastore

from PIL import Image

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


def gcf1_rescale(event, context):

    # Prepare rep variables
    name = event['name']

    # Open client for accessing Storage
    storage_client = storage.Client()

    # Prepare buckets used in process
    source_bucket = storage_client.bucket(os.environ['BUCKET1'])
    target_bucket = storage_client.bucket(os.environ['BUCKET2'])

    # Get uploaded file
    blob = source_bucket.blob(name)

    # Open and rescale
    # Rescales width to 512 and maintains aspect ratio
    im = Image.open(io.BytesIO(blob.download_as_string()), mode='r')
    img_format = im.format

    basewidth = 512
    x, y = im.size
    wpercent = (basewidth/float(x))
    hsize = int((float(y)*float(wpercent)))
    im = im.resize((basewidth, hsize), Image.ANTIALIAS)

    # Save bytes
    byte_arr = io.BytesIO()
    im.save(byte_arr, format=img_format)
    byte_arr = byte_arr.getvalue()

    # Create new blob and upload
    new_blob = target_bucket.blob(name)
    new_blob.upload_from_string(
            byte_arr, content_type=event['contentType']
        )

    blob.make_public()
    new_blob.make_public()

    datastore_client = datastore.Client()
    qu = datastore_client.query(kind='image')
    qu.add_filter('IMG_NAME', '=', name)
    ent = list(qu.fetch())[0]
    ent['RSCL_URL'] = new_blob.public_url
    ent['ORG_URL'] = blob.public_url
    datastore_client.put(ent)


def gcf2_inform(event, context):
    # Create publisher object
    publisher = pubsub_v1.PublisherClient()

    # Publish required info
    publisher.publish(
        'projects/project-ii-gae/topics/rescaled-images',
        b'An image as been rescaled and placed in bucket-2',
        filename=event['name']
        )


def gcf3_vision(event, context):
    client = vision.ImageAnnotatorClient()
    storage_client = storage.Client()
    bucket = storage_client.bucket(os.environ['BUCKET2'])

    blob = bucket.blob(event['attributes']['filename']).download_as_string()

    im = vision.types.Image(content=blob)

    response = client.text_detection(image=im)
    texts = response.text_annotations

    datastore_client = datastore.Client()
    qu = datastore_client.query(kind='image')
    qu.add_filter('IMG_NAME', '=', event['attributes']['filename'])
    ent = list(qu.fetch())[0]
    ent['VISION_API_TEXT'] = str(texts)
    datastore_client.put(ent)

    message = Mail(
        from_email='295013@student.mini.pw.edu.pl',
        to_emails=ent['UPLOADER_EM'],
        subject='Your processed image',
        html_content=f"""
<strong>The following text has been detected in the rescaled imaged:</strong>
<a href="{ent['ORG_IMG']}">Original Image</a>
<a href="{ent['RSCL_IMG']}">Rescaled Image</a>
<p>{texts}</p>"""
            )

    sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
    response = sg.send(message)


# Sources - GCF1
#   google storage blob python ref
#   https://googleapis.dev/python/storage/latest/blobs.html
#
#   google storage buckets python ref
#   https://googleapis.dev/python/storage/latest/buckets.html
#
#   image manipulations with PIL and google storage
#   https://stackoverflow.com/questions/55941068/change-image-size-with-pil-in-a-google-cloud-storage-bucket-from-a-vm-in-gcloud
#
#   blobs saved as strings of bytes
#   https://stackoverflow.com/questions/46078088/how-to-upload-a-bytes-image-on-google-cloud-storage-from-a-python-script
#
#   maintain aspect ratio
#   https://stackoverflow.com/questions/273946/how-do-i-resize-an-image-using-pil-and-maintain-its-aspect-ratio
#
# Sources - GCF2
#   pubsub ref
#   https://googleapis.dev/python/pubsub/latest/index.html
#
#   encoding as bytes
#   https://stackoverflow.com/questions/7585435/best-way-to-convert-string-to-bytes-in-python-3
#
# Sources - GCF3
#   text detection
#   https://cloud.google.com/vision/docs/ocr
#
#   relative paths to container names (pubsup topics)
#   https://cloud.google.com/pubsub/docs/admin#resource_names
#
#   sendgrid
#   https://sendgrid.com/docs/for-developers/sending-email/v3-python-code-example/
