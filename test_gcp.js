const fs = require('fs');
fetch("http://localhost:5001/api/prices?provider=gcp&search=a2-highgpu-1g")
  .then(res => res.json())
  .then(data => {
    const price = data.prices[0];
    const specs = price.specifications || {};
    const specParts = [];
    if (specs.vcpu) specParts.push(`${specs.vcpu} vCPU`);
    if (specs.memory) specParts.push(specs.memory);
    if (specs.gpu) specParts.push(specs.gpu);
    if (specs.network_performance) specParts.push(specs.network_performance);
    if (specs.series) specParts.push(specs.series);
    if (specs.architecture) specParts.push(specs.architecture);
    if (specs.instance_family) specParts.push(specs.instance_family);
    if (specs.machineType) specParts.push(specs.machineType);
    if (specs.cpuPlatform) specParts.push(specs.cpuPlatform);
    if (specs.tier) specParts.push(specs.tier);
    
    const specDisplay = specParts.length > 0 ? specParts.join(' • ') : 'N/A';
    console.log("specDisplay for a2-highgpu-1g:", specDisplay);
  });
