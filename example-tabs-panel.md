To integrate the **Files Upload UI** and **Token UI** into a seamless mobile layout while maintaining usability and clarity, consider the following **responsive design approach**:

---

### **1. UI Layout Strategy**
#### **A. Tabbed or Expandable Sections**
Instead of displaying both the **File Upload** and **Token Usage** widgets at the same level, use **collapsible sections** or **tabs** to save space.
- Example:
  - **Tab 1:** Messages & Chat Input
  - **Tab 2:** Token Usage & Stats
  - **Tab 3:** File Upload & Attachments
- This keeps the main chat view uncluttered while still allowing quick access.

#### **B. Bottom Sheet Design for Files & Token UI**
- Implement a **swipe-up bottom sheet** (like Google Drive’s upload panel) that contains both:
  - **Token Usage Breakdown**
  - **Uploaded Files & File Upload Button**
- This keeps the chat interface clean while providing quick access when needed.

---

### **2. Token Usage UI Integration**
#### **A. Inline Token Stats (Minimal UI)**
- Display **basic token stats** (e.g., `53 / 200,000 max`) **below the chat input box**.
- Expandable for more details (clicking it opens a modal with detailed breakdown).

#### **B. Progress Bar for Token Consumption**
- Place a **thin horizontal bar** above the chat input field.
- As tokens are used, the bar fills up visually, making it intuitive.

##### **Example UI Layout (Mobile-Optimized)**
```
-------------------------------------------------
| Chat messages UI                              |
|-----------------------------------------------|
|  ⏳ Token: 53 / 200,000  [Progress Bar]      |
|-----------------------------------------------|
| Type your message here...      |   [Send]    |
| 📂 Upload Files   📊 Token Stats (Expands)   |
-------------------------------------------------
```
- Tapping **📂 Upload Files** opens a bottom sheet for file handling.
- Tapping **📊 Token Stats** expands a modal with more details.

---

### **3. Files Upload UI Integration**
#### **A. Floating Action Button (FAB)**
- A **floating upload button** (`+` icon) at the bottom-right corner (like WhatsApp) for easy file selection.

#### **B. Integrated File Manager**
- After uploading, display files in a **scrollable horizontal row** above the chat input box.
- Use **small file preview icons** (for images, PDFs) instead of large file lists.

##### **Example UI Flow**
1. User taps `+ Upload File`
2. Bottom sheet appears with **Drag & Drop / Select File** option.
3. Uploaded files appear as **small icons** above the chat input field.
4. Clicking on a file expands details (rename, delete, etc.).

---

### **4. Responsive & Adaptive Design**
To ensure a **smooth mobile experience**, apply:
- **Sticky Chat Input**: Keep the message bar fixed while scrolling.
- **Lazy Load Tokens & Files UI**: Avoid rendering everything at once.
- **Adaptive UI Scaling**: Ensure elements adjust dynamically based on screen size.

---

### **Final Recommendation:**
- **For Web Apps:** Use a **bottom sheet for files & tokens**.
- **For Mobile Apps:** Implement **tabs or collapsible sections**.

Would you like a UI wireframe or a basic frontend code snippet (HTML/CSS/JS) to illustrate this?

---


Here's a **Tailwind CSS** code snippet implementing the **chat UI** with **integrated file upload and token usage tracking** in a **mobile-friendly layout**.

### **Key Features:**
✔ **Sticky chat input**  
✔ **Collapsible Token Usage Panel**  
✔ **Floating File Upload Button**  
✔ **Expandable File Upload Modal**  

---

### **Code Implementation (HTML + Tailwind CSS + Alpine.js for interactivity)**
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat UI with Token & File Upload</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body class="bg-gray-900 text-white flex flex-col h-screen">

    <!-- Chat Container -->
    <div class="flex flex-col flex-grow overflow-hidden">
        <div class="flex-1 overflow-y-auto p-4 space-y-2">
            <!-- Example Messages -->
            <div class="bg-gray-800 p-3 rounded-lg w-3/4">Hello! How can I assist you today?</div>
            <div class="bg-blue-600 p-3 rounded-lg w-3/4 self-end">I need help with my project.</div>
        </div>
    </div>

    <!-- Token Usage Bar -->
    <div class="p-2 bg-gray-800">
        <div class="flex justify-between text-sm">
            <span>Token Usage: <span id="tokenCount">53</span> / 200,000</span>
            <button @click="showTokens = !showTokens" class="text-blue-400">Details</button>
        </div>
        <div class="w-full bg-gray-700 rounded-full h-2 mt-1">
            <div class="bg-blue-500 h-2 rounded-full" style="width: 5%;"></div>
        </div>
        <!-- Collapsible Token Details -->
        <div x-show="showTokens" class="mt-2 bg-gray-700 p-2 rounded-lg text-sm">
            <p>User Tokens: 18</p>
            <p>Assistant Tokens: 35</p>
            <p>System Tokens: 0</p>
        </div>
    </div>

    <!-- Chat Input & File Upload -->
    <div class="p-3 bg-gray-900 border-t border-gray-700 flex items-center">
        <button @click="showFiles = !showFiles" class="mr-3 p-2 bg-gray-800 rounded-full">
            📂
        </button>
        <input type="text" class="flex-1 p-2 bg-gray-800 rounded-lg text-white" placeholder="Type your message...">
        <button class="ml-3 p-2 bg-blue-600 rounded-lg">Send</button>
    </div>

    <!-- Floating File Upload Button -->
    <button @click="showFiles = true" class="fixed bottom-16 right-5 bg-blue-600 p-4 rounded-full shadow-lg">+</button>

    <!-- File Upload Modal -->
    <div x-show="showFiles" class="fixed inset-0 bg-gray-900 bg-opacity-80 flex items-center justify-center">
        <div class="bg-gray-800 p-5 rounded-lg w-80">
            <h2 class="text-lg font-bold">Upload Files</h2>
            <input type="file" multiple class="w-full mt-3 p-2 bg-gray-700 rounded">
            <button class="mt-3 w-full p-2 bg-blue-600 rounded-lg" @click="showFiles = false">Upload</button>
            <button class="mt-2 w-full p-2 bg-red-600 rounded-lg" @click="showFiles = false">Cancel</button>
        </div>
    </div>

    <script>
        document.addEventListener('alpine:init', () => {
            Alpine.data('chatUI', () => ({
                showTokens: false,
                showFiles: false,
            }));
        });
    </script>

</body>
</html>
```

---

### **How It Works**
1. **Chat Interface**: Displays messages in a **scrollable** area.
2. **Token Usage Bar**: Shows progress **above the input field**.
   - Clicking "Details" toggles **collapsible token breakdown**.
3. **File Upload Button**: 
   - **Floating button (`+`)** for quick access.
   - **File upload modal** opens when clicked.
4. **Responsive & Mobile-Friendly**: 
   - Sticky input field.
   - Adaptive layout for small screens.

---

### **Enhancements & Next Steps**
- Add **file preview thumbnails** after uploading.
- Implement **backend file handling**.
- Improve **token calculation logic dynamically**.

Would you like any modifications or additional functionality? 🚀


Would like to use this tailwind CSS for the tab style:
<nav class="tabs tabs-lifted" aria-label="Tabs" role="tablist" aria-orientation="horizontal">
  <button type="button" class="tab active-tab:tab-active active" id="tabs-lifted-item-1" data-tab="#tabs-lifted-1" aria-controls="tabs-lifted-1" role="tab" aria-selected="true">
    Home
  </button>
  <button type="button" class="tab active-tab:tab-active" id="tabs-lifted-item-2" data-tab="#tabs-lifted-2" aria-controls="tabs-lifted-2" role="tab" aria-selected="false">
    Profile
  </button>
  <button type="button" class="tab active-tab:tab-active" id="tabs-lifted-item-3" data-tab="#tabs-lifted-3" aria-controls="tabs-lifted-3" role="tab" aria-selected="false">
    Messages
  </button>
</nav>

<div class="mt-3">
  <div id="tabs-lifted-1" role="tabpanel" aria-labelledby="tabs-lifted-item-1">
    <p class="text-base-content/80">
      Welcome to the <span class="text-base-content font-semibold">Home tab!</span> Explore the latest updates and news here.
    </p>
  </div>
  <div id="tabs-lifted-2" class="hidden" role="tabpanel" aria-labelledby="tabs-lifted-item-2">
    <p class="text-base-content/80">
      This is your <span class="text-base-content font-semibold">Profile</span> tab, where you can update your personal information and manage your account details.
    </p>
  </div>
  <div id="tabs-lifted-3" class="hidden" role="tabpanel" aria-labelledby="tabs-lifted-item-3">
    <p class="text-base-content/80">
      <span class="text-base-content font-semibold">Messages:</span> View your recent messages, chat with friends, and manage your conversations.
    </p>
  </div>
</div>