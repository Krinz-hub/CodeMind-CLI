document.addEventListener('DOMContentLoaded', () => {
    // Like functionality
    const likeBtns = document.querySelectorAll('.like-btn');
    likeBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            this.classList.toggle('fa-solid');
            this.classList.toggle('fa-regular');
            if (this.classList.contains('fa-solid')) {
                this.style.color = '#ed4956';
            } else {
                this.style.color = 'inherit';
            }
        });
    });

    // Save functionality
    const saveBtns = document.querySelectorAll('.save-btn');
    saveBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            this.classList.toggle('fa-solid');
            this.classList.toggle('fa-regular');
        });
    });

    // Story click effect
    const storyRings = document.querySelectorAll('.story-ring');
    storyRings.forEach(ring => {
        ring.addEventListener('click', () => {
            console.log('Viewing story...');
        });
    });
});