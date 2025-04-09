function createNewVideoElement(nick, isScreen = false, homeElemnt = undefined){
    homeElemnt = homeElemnt || document.getElementById('video-home');

    let videoElement = document.createElement('video');
    videoElement.classList.add("webrtc-video");
    videoElement.setAttribute('playsinline', '');
    videoElement.setAttribute('autoplay', true);
    videoElement.setAttribute('nick', nick);
    videoElement.setAttribute('isScreen', isScreen)

    homeElemnt.appendChild(videoElement);

    return videoElement;
}

function toggleScreenVideo(screenElement){
    screenElement = screenElement || document.getElementById('local-screen-video');
    screenElement.classList.toggle('hidden');
}

function isExist(nick) {
    return nick == selfNick || document.querySelectorAll(`video[nick="${nick}"]`).length > 0;
}

function removeVideo(nick, isScreen = undefined){
    if (isScreen == undefined){
        document.querySelectorAll(`video[nick="${nick}"]`).forEach(elem => {
            elem.remove()
        });
    } else {
        document.querySelectorAll(`video[nick="${nick}"][isScreen=${isScreen}]`).forEach(elem => {
            elem.remove()
        });
    }
}