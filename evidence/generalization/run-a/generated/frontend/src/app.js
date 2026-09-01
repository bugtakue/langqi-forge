const statusNode = document.querySelector("#status");
const form = document.querySelector("#change-form");
const requesterInput = document.querySelector("#requester");
const summaryInput = document.querySelector("#summary");
const riskSelect = document.querySelector("#risk");
const errorNode = document.querySelector("#change-error");
const requestsContainer = document.querySelector("#requests-container");

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

function render(state) {
  requestsContainer.replaceChildren();
  for (const request of state.requests || []) {
    const article = document.createElement("article");
    article.setAttribute("aria-label", request.summary);
    
    const header = document.createElement("h3");
    header.textContent = request.summary;
    article.appendChild(header);
    
    const details = document.createElement("div");
    details.innerHTML = `
      <p>Requester: ${request.requester}</p>
      <p>Risk: ${request.risk}</p>
      <p>Status: ${request.status}</p>
    `;
    article.appendChild(details); // This line was missing
    
    if (request.status === "Pending") {
      const approvalSection = document.createElement("div");
      approvalSection.className = "approval-section";
      approvalSection.innerHTML = `
        <label for="reviewer-${request.id}">Reviewer</label>
        <input id="reviewer-${request.id}" name="reviewer" type="text" autocomplete="off" />
        <p class="error" role="alert" id="approval-error-${request.id}"></p>
        <button type="button" class="approve-btn" data-id="${request.id}">Approve</button>
        <button type="button" class="execute-btn" data-id="${request.id}" disabled>Execute</button>
      `;
      article.appendChild(approvalSection);
    } else if (request.status === "Approved") {
      const executedSection = document.createElement("div");
      executedSection.innerHTML = `
        <p>Approved by: ${request.approvedBy}</p>
        <button type="button" class="execute-btn" data-id="${request.id}">Execute</button>
      `;
      article.appendChild(executedSection);
    } else if (request.status === "Executed") {
      const executedSection = document.createElement("div");
      executedSection.innerHTML = `
        <p>Approved by: ${request.approvedBy}</p>
      `;
      article.appendChild(executedSection);
    }
    
    requestsContainer.appendChild(article);
  }
  
  // Add event listeners for approve and execute buttons
  document.querySelectorAll(".approve-btn").forEach(button => {
    button.addEventListener("click", handleApprove);
  });
  
  document.querySelectorAll(".execute-btn").forEach(button => {
    button.addEventListener("click", handleExecute);
  });
}

async function load() {
  statusNode.textContent = "Loading";
  try {
    render(await request("/api/state"));
    statusNode.textContent = "Ready";
  } catch (error) {
    statusNode.textContent = error.message;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const requester = requesterInput.value.trim();
  const summary = summaryInput.value.trim();
  const risk = riskSelect.value;
  
  if (!requester || !summary) {
    errorNode.textContent = "Requester and summary are required";
    return;
  }
  
  errorNode.textContent = "";
  
  const current = await request("/api/state");
  const requests = [...(current.requests || []), { 
    id: crypto.randomUUID(), 
    requester, 
    summary, 
    risk, 
    status: "Pending" 
  }];
  
  render(await request("/api/state", { method: "PUT", body: JSON.stringify({ requests }) }));
  requesterInput.value = "";
  summaryInput.value = "";
  riskSelect.value = "Low";
  statusNode.textContent = "Change request submitted";
});

async function handleApprove(event) {
  const requestId = event.target.dataset.id;
  const reviewerInput = document.querySelector(`#reviewer-${requestId}`);
  const errorElement = document.querySelector(`#approval-error-${requestId}`);
  const reviewer = reviewerInput.value.trim();
  
  if (!reviewer) {
    errorElement.textContent = "Reviewer is required";
    return;
  }
  
  const currentState = await request("/api/state");
  const requestItem = currentState.requests.find(r => r.id === requestId);
  
  if (!requestItem) {
    errorElement.textContent = "Request not found";
    return;
  }
  
  if (requestItem.requester.toLowerCase() === reviewer.toLowerCase()) {
    errorElement.textContent = "Reviewer must differ from requester";
    return;
  }
  
  errorElement.textContent = "";
  
  const updatedRequests = currentState.requests.map(req => {
    if (req.id === requestId) {
      return { ...req, status: "Approved", approvedBy: reviewer };
    }
    return req;
  });
  
  render(await request("/api/state", { method: "PUT", body: JSON.stringify({ requests: updatedRequests }) }));
  statusNode.textContent = "Request approved";
}

async function handleExecute(event) {
  const requestId = event.target.dataset.id;
  
  const currentState = await request("/api/state");
  const updatedRequests = currentState.requests.map(req => {
    if (req.id === requestId && req.status === "Approved") {
      return { ...req, status: "Executed" };
    }
    return req;
  });
  
  render(await request("/api/state", { method: "PUT", body: JSON.stringify({ requests: updatedRequests }) }));
  statusNode.textContent = "Request executed";
}

document.querySelector("#refresh-button").addEventListener("click", load);
load();
