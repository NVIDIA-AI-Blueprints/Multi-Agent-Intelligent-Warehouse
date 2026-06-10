export default function startParticles() {
  if (document.getElementById("nvidia-particles")) {
    return;
  }

  var canvas = document.createElement("canvas");
  var ctx = canvas.getContext("2d");
  var reducedMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var particles = [];
  var width = 0;
  var height = 0;
  var dpr = 1;
  var animationFrame = 0;

  if (!ctx) {
    return;
  }

  canvas.id = "nvidia-particles";
  canvas.setAttribute("aria-hidden", "true");
  document.body.prepend(canvas);

  function particleCount() {
    if (window.innerWidth < 720) {
      return 48;
    }

    return Math.min(125, Math.floor(window.innerWidth / 12));
  }

  function createParticle() {
    var speed = 0.1 + Math.random() * 0.18;
    var angle = Math.random() * Math.PI * 2;

    return {
      x: Math.random() * width,
      y: Math.random() * height,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      radius: 1.1 + Math.random() * 2.3,
      alpha: 0.34 + Math.random() * 0.5
    };
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    var count = particleCount();
    while (particles.length < count) {
      particles.push(createParticle());
    }
    particles.length = count;
  }

  function drawParticle(particle) {
    ctx.beginPath();
    ctx.fillStyle = "rgba(142, 212, 0, " + particle.alpha + ")";
    ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
    ctx.fill();

    ctx.beginPath();
    ctx.fillStyle = "rgba(118, 185, 0, " + (particle.alpha * 0.13) + ")";
    ctx.arc(particle.x, particle.y, particle.radius * 4.2, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawConnections() {
    var maxDistance = Math.min(190, Math.max(112, width / 7.5));

    for (var i = 0; i < particles.length; i += 1) {
      for (var j = i + 1; j < particles.length; j += 1) {
        var a = particles[i];
        var b = particles[j];
        var dx = a.x - b.x;
        var dy = a.y - b.y;
        var distance = Math.sqrt(dx * dx + dy * dy);

        if (distance > maxDistance) {
          continue;
        }

        ctx.beginPath();
        ctx.strokeStyle = "rgba(118, 185, 0, " + ((1 - distance / maxDistance) * 0.22) + ")";
        ctx.lineWidth = 1;
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
    }
  }

  function update() {
    for (var i = 0; i < particles.length; i += 1) {
      var particle = particles[i];

      particle.x += particle.vx;
      particle.y += particle.vy;

      if (particle.x < -20) {
        particle.x = width + 20;
      } else if (particle.x > width + 20) {
        particle.x = -20;
      }

      if (particle.y < -20) {
        particle.y = height + 20;
      } else if (particle.y > height + 20) {
        particle.y = -20;
      }
    }
  }

  function render() {
    ctx.clearRect(0, 0, width, height);
    drawConnections();

    for (var i = 0; i < particles.length; i += 1) {
      drawParticle(particles[i]);
    }

    if (!reducedMotion) {
      update();
      animationFrame = window.requestAnimationFrame(render);
    }
  }

  window.addEventListener("resize", function () {
    window.cancelAnimationFrame(animationFrame);
    resize();
    render();
  });

  resize();
  render();
}
