function createNewVideoElement(nick, homeElemnt){
    homeElemnt = homeElemnt || document.getElementById('video-home');

    let videoElement = document.createElement('video');
    videoElement.classList.add("webrtc-video");
    videoElement.setAttribute('playsinline', '');
    videoElement.setAttribute('autoplay', true);
    videoElement.setAttribute('nick', nick);

    homeElemnt.appendChild(videoElement);

    return videoElement;
}