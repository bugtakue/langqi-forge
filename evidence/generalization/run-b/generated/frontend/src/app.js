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
  for (const req of state.requests || []) {
    const card = document.createElement("article");
    card.className = "request-card";
    card.setAttribute("aria-label", req.summary);
    
    const header = document.createElement("h3");
    header.textContent = req.summary;
    card.appendChild(header);
    
    const details = document.createElement("div");
    details.className = "request-details";
    details.innerHTML = `
      <div><strong>Requester:</strong> ${req.requester}</div>
      <div><strong>Risk:</strong> ${req.risk}</div>
      <div><strong>Status:</strong> ${req.status}</div>
    `;
    card.appendChild(details);
    
    if (req.status === "Pending") {
      const approvalSection = document.createElement("div");
      approvalSection.className = "approval-section";
      approvalSection.innerHTML = `
        <label for="reviewer-${req.id}">Reviewer</label>
        <input id="reviewer-${req.id}" name="reviewer" type="text" autocomplete="off" />
        <div class="action-buttons">
          <button type="button" class="approve-btn" data-id="${req.id}">Approve</button>
          <button type="button" class="execute-btn" data-id="${req.id}" disabled>Execute</button>
        </div>
        <p class="error" role="alert" id="approval-error-${req.id}"></p>
      `;
      card.appendChild(approvalSection);
    } else if (req.status === "Approved") {
      const approvalSection = document.createElement("div");
      approvalSection.className = "approval-section";
      approvalSection.innerHTML = `
        <div class="approved-by"><strong>Approved by:</strong> ${req.reviewer}</div>
        <div class="action-buttons">
          <button type="button" class="execute-btn" data-id="${req.id}">Execute</button>
        </div>
      `;
      card.appendChild(approvalSection);
    } else if (req.status === "Executed") {
      const executedSection = document.createElement("div");
      executedSection.className = "approval-section";
      executedSection.innerHTML = `
        <div class="approved-by"><strong>Approved by:</strong> ${req.reviewer}</div>
        <div><strong>Executed</strong></div>
      `;
      card.appendChild(executedSection);
    }
    
    requestsContainer.appendChild(card);
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
  
  errorElement.textContent = "";
  
  try {
    const state = await request("/api/state");
    const requestObj = state.requests.find(r => r.id === requestId);
    
    if (!requestObj) {
      errorElement.textContent = "Request not found";
      return;
    }
    
    if (requestObj.requester.toLowerCase() === reviewer.toLowerCase()) {
      errorElement.textContent = "Reviewer must differ from requester";
      return;
    }
    
    // Update the request status and add reviewer
    const updatedRequests = state.requests.map(req => {
      if (req.id === requestId) {
        return { ...req, status: "Approved", reviewer };
      }
      return req;
    });
    
    render(await request("/api/state", { method: "PUT", body: JSON.stringify({ requests: updatedRequests }) }));
    statusNode.textContent = "Request approved";
  } catch (error) {
    errorElement.textContent = error.message;
  }
}

async function handleExecute(event) {
  const requestId = event.target.dataset.id;
  
  try {
    const state = await request("/api/state");
    const updatedRequests = state.requests.map(req => {
      if (req.id === requestId) {
        return { ...req, status: "Executed" };
      }
      return req;
    });
    
    render(await request("/api/state", { method: "PUT", body: JSON.stringify({ requests: updatedRequests }) }));
    statusNode.textContent = "Request executed";
  } catch (error) {
    statusNode.textContent = error.message;
  }
}

document.querySelector("#refresh-button").addEventListener("click", load);
load();
