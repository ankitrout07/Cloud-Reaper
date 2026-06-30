const price = {
  sku: "a2-highgpu-1g",
  name: "a2-highgpu-1g",
  service: "Compute Engine",
  region: "us-west8",
  description: "",
  specifications: {
    vcpu: null,
    memory: null,
    gpu: null,
    network_performance: null,
    machineType: null,
    cpuPlatform: null
  }
};
const pricingType = "hourly";
const priceValue = 3.673385;

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

const html = `
    <tr class="border-b border-white/5 hover:bg-white/5 transition">
        <td class="p-4">
            <div class="text-white font-semibold text-sm">${price.sku || price.name || 'Unknown SKU'}</div>
            <div class="text-slate-500 text-xs mt-0.5">${price.description || ''}</div>
        </td>
        <td class="p-4 text-slate-300 text-sm">${price.service || 'Compute'}</td>
        <td class="p-4">
            <span class="px-2 py-1 bg-cyan-500/10 text-cyan-400 text-xs rounded border border-cyan-500/20">${price.region || 'Unknown'}</span>
        </td>
        <td class="p-4">
            <div class="text-slate-300 text-xs">${specDisplay}</div>
        </td>
        <td class="p-4">
            <span class="text-white font-mono text-sm metric-value">$${Number(priceValue).toFixed(4)}</span>
            <span class="text-slate-500 text-xs ml-1">/ ${pricingType}</span>
        </td>
        <td class="p-4">
            <button onclick='addToCart(${JSON.stringify(price).replace(/'/g, "\\'")})' class="px-3 py-2 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 rounded-lg text-xs font-bold uppercase tracking-wider transition">
                <i class="fas fa-plus mr-1"></i> Add
            </button>
        </td>
    </tr>
`;
console.log(html);
