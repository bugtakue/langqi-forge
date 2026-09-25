// Synthetic local diagnostic only: no contest business logic or real account.
const details = document.createElement("p");
details.textContent = "Attached result";
document.body.append(document.createTextNode("Nested argument: "), details);

const input = document.createElement("input");
input.type = "text";
input.setAttribute("aria-label", "Diagnostic value");
document.body.append(document.createTextNode("Value: "), input);

const save = document.createElement("button");
save.textContent = "Echo value";
document.body.append(save);

const feedback = document.createElement("p");
feedback.setAttribute("role", "status");
document.body.append(feedback);
save.addEventListener("click", () => {
  feedback.textContent = "Value: " + input.value;
});
