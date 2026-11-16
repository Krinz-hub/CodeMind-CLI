const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

// Game variables
let frames = 0;

// Bird object
const bird = {
    x: 50,
    y: 150,
    radius: 10,
    speed: 0,
    gravity: 0.25,
    jump: -4.6,
    
    draw: function() {
        ctx.fillStyle = "#f1c40f";
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        
        // Eye
        ctx.fillStyle = "#fff";
        ctx.beginPath();
        ctx.arc(this.x + 5, this.y - 5, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        
        // Pupil
        ctx.fillStyle = "#000";
        ctx.beginPath();
        ctx.arc(this.x + 6, this.y - 5, 2, 0, Math.PI * 2);
        ctx.fill();
    },
    
    update: function() {
        this.speed += this.gravity;
        this.y += this.speed;
        
        // Floor collision
        if (this.y + this.radius >= canvas.height) {
            this.y = canvas.height - this.radius;
            gameOver();
        }
        
        // Ceiling collision
        if (this.y - this.radius <= 0) {
            this.y = this.radius;
            this.speed = 0;
        }
    },
    
    flap: function() {
        this.speed = this.jump;
    }
};

// Pipes object
const pipes = {
    position: [],
    w: 50,
    h: 400,
    gap: 120,
    dx: 2,
    
    draw: function() {
        for (let i = 0; i < this.position.length; i++) {
            let p = this.position[i];
            let topY = p.y;
            let bottomY = p.y + this.h + this.gap;
            
            // Top Pipe
            ctx.fillStyle = "#2ecc71";
            ctx.fillRect(p.x, topY, this.w, this.h);
            ctx.strokeRect(p.x, topY, this.w, this.h);
            
            // Bottom Pipe
            ctx.fillRect(p.x, bottomY, this.w, this.h);
            ctx.strokeRect(p.x, bottomY, this.w, this.h);
        }
    },
    
    update: function() {
        // Add new pipe every 120 frames
        if (frames % 120 === 0) {
            this.position.push({
                x: canvas.width,
                y: -150 * (Math.random() + 1)
            });
        }
        
        for (let i = 0; i < this.position.length; i++) {
            let p = this.position[i];
            p.x -= this.dx;
            
            // Collision detection
            let bottomPipeY = p.y + this.h + this.gap;
            
            // Top pipe collision
            if (bird.x + bird.radius > p.x && 
                bird.x - bird.radius < p.x + this.w && 
                bird.y - bird.radius < p.y + this.h) {
                gameOver();
            }
            
            // Bottom pipe collision
            if (bird.x + bird.radius > p.x && 
                bird.x - bird.radius < p.x + this.w && 
                bird.y + bird.radius > bottomPipeY) {
                gameOver();
            }
            
            // Remove pipes that have gone off screen
            if (p.x + this.w <= 0) {
                this.position.shift();
                score.value += 1;
                score.best = Math.max(score.value, score.best);
                localStorage.setItem("flappy_best", score.best);
            }
        }
    },
    
    reset: function() {
        this.position = [];
    }
};

// Background (simple ground)
const bg = {
    draw: function() {
        ctx.fillStyle = "#e74c3c";
        ctx.fillRect(0, canvas.height - 20, canvas.width, 20);
    }
};

// Score
const score = {
    best: localStorage.getItem("flappy_best") || 0,
    value: 0,
    
    draw: function() {
        ctx.fillStyle = "#FFF";
        ctx.strokeStyle = "#000";
        
        if (gameState.current == gameState.states.GAME) {
            ctx.font = "35px Arial";
            ctx.fillText(this.value, canvas.width / 2, 50);
            ctx.strokeText(this.value, canvas.width / 2, 50);
        }
    },
    
    reset: function() {
        this.value = 0;
    }
};

// Game State
const gameState = {
    current: 0,
    states: {
        GETREADY: 0,
        GAME: 1,
        GAMEOVER: 2
    }
};

// Controls
document.getElementById('startBtn').addEventListener('click', startGame);
document.getElementById('restartBtn').addEventListener('click', resetGame);
canvas.addEventListener('click', flap);
document.addEventListener('keydown', function(e) {
    if (e.code === 'Space') {
        if (gameState.current == gameState.states.GAME) {
            bird.flap();
        } else if (gameState.current == gameState.states.GETREADY) {
            startGame();
        } else if (gameState.current == gameState.states.GAMEOVER) {
            resetGame();
        }
    }
});

function startGame() {
    gameState.current = gameState.states.GAME;
    document.getElementById('startScreen').classList.add('hidden');
}

function resetGame() {
    bird.speed = 0;
    bird.y = 150;
    pipes.reset();
    score.reset();
    frames = 0;
    gameState.current = gameState.states.GETREADY;
    document.getElementById('gameOverScreen').classList.add('hidden');
    document.getElementById('startScreen').classList.remove('hidden');
}

function flap() {
    if (gameState.current == gameState.states.GAME) {
        bird.flap();
    }
}

function gameOver() {
    gameState.current = gameState.states.GAMEOVER;
    document.getElementById('finalScore').innerText = score.value;
    document.getElementById('gameOverScreen').classList.remove('hidden');
}

// Game Loop
function loop() {
    // Update
    if (gameState.current == gameState.states.GAME) {
        bird.update();
        pipes.update();
    }
    
    // Draw
    ctx.fillStyle = "#70c5ce";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    pipes.draw();
    bg.draw();
    bird.draw();
    score.draw();
    
    frames++;
    requestAnimationFrame(loop);
}

loop();