const video = document.getElementById('camera');
const captureButton = document.getElementById('capture-button');
const captureOptions = document.getElementById('capture-options');
const imageInput = document.getElementById('image-data');
const cameraError = document.getElementById('camera-error');
const canvas = document.createElement('canvas');

let stream;

const constraints = {
    video: {
        facingMode: { ideal: 'environment' },
        width: { ideal: 1280 },
        height: { ideal: 720 }
    }
};

navigator.mediaDevices.getUserMedia(constraints)
    .then(function (s) {
        stream = s;
        video.srcObject = stream;
        video.style.display = 'block';
        video.play();
    })
    .catch(function (err) {
        console.error("Camera Access Error:", err);
        // Hide camera UI and show friendly error
        video.style.display = 'none';
        captureButton.style.display = 'none';
        if (cameraError) cameraError.style.display = 'block';
    });

function capture() {
    if (video.readyState < video.HAVE_ENOUGH_DATA) {
        alert("Camera isn't ready yet. Please wait a moment.");
        return;
    }

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    const dataURL = canvas.toDataURL('image/jpeg', 0.8);
    imageInput.value = dataURL;

    video.pause();
    captureButton.style.display = 'none';
    captureOptions.style.display = 'flex';
}

function retry() {
    video.play();
    captureButton.style.display = 'block';
    captureOptions.style.display = 'none';
    imageInput.value = '';
}