require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config({ path: "C:\\Users\\zvbrs\\Desktop\\Medledeger2\\.env" });
console.log("ALCHEMY_URL loaded:", process.env.ALCHEMY_URL ? "YES" : "NO");
/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: "0.8.19",
  networks: {
    // Local Hardhat network — kept for local testing if needed
    hardhat: {
      chainId: 1337,
      mining: {
        auto: true,
        interval: 0
      }
    },
    localhost: {
      url: "http://127.0.0.1:8545",
      chainId: 1337
    },
    // ✅ Sepolia Testnet — permanent global blockchain
    sepolia: {
      url: process.env.ALCHEMY_URL,
      accounts: [process.env.PRIVATE_KEY],
      chainId: 11155111,
    },
  },
  paths: {
    sources:   "./contracts",
    tests:     "./test",
    cache:     "./cache",
    artifacts: "./artifacts"
  }
};