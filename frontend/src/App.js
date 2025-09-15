import React, { useState } from 'react';
import axios from 'axios';

function App() {
  const [file, setFile] = useState(null);
  const [reportPath, setReportPath] = useState('');

  const handleUpload = async () => {
    const formData = new FormData();
    formData.append('pdf', file);

    const res = await axios.post('http://localhost:5000/upload', formData);
    setReportPath(res.data.report);
  };

  return (
    <div>
      <h2>PDF Accessibility Checker</h2>
      <input type="file" accept="application/pdf" onChange={e => setFile(e.target.files[0])} />
      <button onClick={handleUpload}>Upload & Check</button>

      {reportPath && (
        <a href={`http://localhost:5000/download/${reportPath}`} download>
          Download Report
        </a>
      )}
    </div>
  );
}

export default App;
