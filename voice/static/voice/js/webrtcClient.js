let chatSocket;
let selfNick;
let roomName;

const hangupButton = document.getElementById('hangupButton');
hangupButton.disabled = true;

const localVideo = document.getElementById('localVideo');
const remoteVideo = document.getElementById('remoteVideo');

let pc1;
let localStream;

document.addEventListener("DOMContentLoaded", async (e) => {
    roomName = JSON.parse(document.getElementById('room-code').textContent);
    localStream = await navigator.mediaDevices.getUserMedia({audio: true, video: false});
    localVideo.srcObject = localStream;

    hangupButton.disabled = false;
    if (location.protocol == 'https:'){
        chatSocket = new WebSocket(
            'wss://'
            + window.location.host
            + '/ws/voice/'
            + roomName
            + '/'
        );
    } else {
        chatSocket = new WebSocket(
            'ws://'
            + window.location.host
            + '/ws/voice/'
            + roomName
            + '/'
        );
    }

    chatSocket.onmessage = (e) => {
        const data = JSON.parse(e.data)
        console.log(data);
        if (!localStream) {
            console.log('not ready yet');
            return;
        }

        let sender = data.sender;
        delete data.sender;
        delete data.to;

        switch (data.type) {
            case 'hello':
                handleHello(data);
                break;
            case 'offer':
                handleOffer(data, sender);
                break;
            case 'answer':
                handleAnswer(data);
                break;
            case 'candidate':
                handleCandidate(data);
                break;
            case 'ready':
                if (pc1) {
                    console.log('already in call, ignoring');
                    return;
                }
                makeCall();
                break;
            case 'bye':
                if (pc1) {
                    hangup();
                }
                break;
            default:
                console.log('unhandled', e);
                break;
        }
    };

});

hangupButton.onclick = async () => {
    hangup();
    chatSocket.send(JSON.stringify({type: 'bye'}));
};

async function hangup() {
    if (pc1) {
        pc1.close();
        pc1 = null;
    }
    localStream.getTracks().forEach(track => track.stop());
    localStream = null;
    hangupButton.disabled = true;
};

function createPeerConnection() {
    pc1 = new RTCPeerConnection();
    pc1.onicecandidate = e => {
        if (e.candidate) {
            const message = {
                type: 'candidate',
                candidate: null,
            };
            message.candidate = e.candidate.candidate;
            message.sdpMid = e.candidate.sdpMid;
            message.sdpMLineIndex = e.candidate.sdpMLineIndex;
            chatSocket.send(JSON.stringify(message));
        }
    };
    pc1.ontrack = e => {
        remoteVideo.srcObject = e.streams[0];
    }
    localStream.getTracks().forEach(track => pc1.addTrack(track, localStream));
}

async function makeCall() {
    createPeerConnection();

    const offer = await pc1.createOffer();
    chatSocket.send(JSON.stringify({type: 'offer', sdp: offer.sdp}));
    await pc1.setLocalDescription(offer);
}

function handleHello(hello){
    selfNick = hello.nick;
}

async function handleOffer(offer, sender) {
    if (pc1) {
        console.error('existing peerconnection');
        return;
    }
    createPeerConnection();

    await pc1.setRemoteDescription(offer);

    const answer = await pc1.createAnswer();
    chatSocket.send(JSON.stringify({
        type: 'answer',
        sdp: answer.sdp,
        to: sender
    }));
    await pc1.setLocalDescription(answer);
}

async function handleAnswer(answer) {
    if (!pc1) {
        console.error('no peerconnection');
        return;
    }
    await pc1.setRemoteDescription(answer);
}

async function handleCandidate(candidate) {
    if (!pc1) {
        console.error('no peerconnection');
        return;
    }
    if (!candidate.candidate) {
        await pc1.addIceCandidate(null);
    } else {
        await pc1.addIceCandidate(candidate);
    }
}