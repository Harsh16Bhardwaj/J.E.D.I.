document.querySelectorAll("nav a").forEach((link) => {
  const current = location.pathname.split("/").pop() || "index.html";
  if (link.getAttribute("href") === current) link.classList.add("active");
});

document.querySelectorAll("pre").forEach((block) => {
  const wrapper = document.createElement("div");
  wrapper.className = "code-wrap";
  block.parentNode.insertBefore(wrapper, block);
  wrapper.appendChild(block);
  const button = document.createElement("button");
  button.className = "copy";
  button.type = "button";
  button.textContent = "COPY";
  button.addEventListener("click", async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(block.innerText);
      } else {
        const input = document.createElement("textarea");
        input.value = block.innerText;
        input.style.position = "fixed";
        input.style.opacity = "0";
        document.body.appendChild(input);
        input.select();
        document.execCommand("copy");
        input.remove();
      }
      button.textContent = "COPIED";
    } catch {
      button.textContent = "SELECT";
    }
    setTimeout(() => { button.textContent = "COPY"; }, 1200);
  });
  wrapper.appendChild(button);
});
