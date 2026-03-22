/**
 * deploy.js
 * =========
 * Deploys MedLedger.sol to the local Hardhat network.
 *
 * Run:
 *   cd blockchain
 *   npx hardhat run scripts/deploy.js --network localhost
 *
 * After running, this script writes two files back to the project root:
 *   ../blockchain_address.json   ← contract address Flask reads
 *   ../blockchain_abi.json       ← contract ABI Flask reads
 *
 * These two files are all blockchain_bridge.py needs.
 */

const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  console.log("Deploying MedLedger contract...");

  const [deployer] = await ethers.getSigners();
  console.log(`Deployer address: ${deployer.address}`);
  console.log(`Deployer balance: ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH`);

  // Deploy
  const MedLedger = await ethers.getContractFactory("MedLedger");
  const contract  = await MedLedger.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log(`\nMedLedger deployed at: ${address}`);

  // ── Write address file ────────────────────────────────────────────────────
  const addressFile = path.join(__dirname, "../../blockchain_address.json");
  fs.writeFileSync(
    addressFile,
    JSON.stringify({ address, network: "localhost", chainId: 1337 }, null, 2)
  );
  console.log(`Address saved to: ${addressFile}`);

  // ── Write ABI file ────────────────────────────────────────────────────────
  const artifactPath = path.join(
    __dirname,
    "../artifacts/contracts/MedLedger.sol/MedLedger.json"
  );

  if (fs.existsSync(artifactPath)) {
    const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));
    const abiFile = path.join(__dirname, "../../blockchain_abi.json");
    fs.writeFileSync(abiFile, JSON.stringify(artifact.abi, null, 2));
    console.log(`ABI saved to: ${abiFile}`);
  } else {
    console.warn("Artifact not found — run 'npx hardhat compile' first.");
  }

  console.log("\nDeployment complete!");
  console.log("Next: Start Flask app and the blockchain bridge will connect automatically.");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
