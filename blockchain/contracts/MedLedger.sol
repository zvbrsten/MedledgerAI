// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * MedLedger.sol
 * =============
 * Immutable audit trail for Federated Learning events.
 *
 * Three event types are logged:
 *   1. HospitalSubmission  — hospital submitted local model weights
 *   2. GlobalAggregation   — server completed FedAvg and produced global model
 *   3. HospitalLogin       — hospital logged in to the portal
 *
 * Nothing stored here contains patient data.
 * Only hashes, IDs, round numbers, and metrics.
 *
 * Deployed once on local Hardhat network.
 * Flask reads it via web3.py (blockchain_bridge.py).
 */

contract MedLedger {

    // ── OWNER ────────────────────────────────────────────────────────────────
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    // ── STRUCTS ──────────────────────────────────────────────────────────────

    struct SubmissionEvent {
        uint256 id;
        string  hospitalId;       // e.g. "hospital_1"
        uint256 roundNumber;
        string  weightsHash;      // SHA-256 of weights.pt
        uint256 accuracyX10000;   // accuracy * 10000  (e.g. 0.8638 → 8638)
        uint256 numSamples;
        uint256 timestamp;        // Unix timestamp
    }

    struct AggregationEvent {
        uint256 id;
        uint256 roundNumber;
        string  globalModelHash;  // SHA-256 of global_model_roundN.pt
        string  hospitalsList;    // comma-separated: "hospital_1,hospital_2,..."
        uint256 totalSamples;
        uint256 timestamp;
    }

    struct LoginEvent {
        uint256 id;
        string  hospitalId;
        uint256 timestamp;
    }

    // ── STORAGE ──────────────────────────────────────────────────────────────

    SubmissionEvent[]   public submissions;
    AggregationEvent[]  public aggregations;
    LoginEvent[]        public logins;

    // ── EVENTS (Solidity events — emitted so web3.py can filter them) ────────

    event SubmissionLogged(
        uint256 indexed id,
        string  hospitalId,
        uint256 indexed roundNumber,
        string  weightsHash,
        uint256 accuracyX10000,
        uint256 numSamples,
        uint256 timestamp
    );

    event AggregationLogged(
        uint256 indexed id,
        uint256 indexed roundNumber,
        string  globalModelHash,
        string  hospitalsList,
        uint256 totalSamples,
        uint256 timestamp
    );

    event LoginLogged(
        uint256 indexed id,
        string  hospitalId,
        uint256 timestamp
    );

    // ── WRITE FUNCTIONS ──────────────────────────────────────────────────────

    /**
     * Log a hospital model weight submission.
     * Called by Flask after saving weights.pt successfully.
     *
     * @param hospitalId      Hospital identifier string
     * @param roundNumber     FL round number
     * @param weightsHash     SHA-256 hex string of the weights file
     * @param accuracyX10000  accuracy * 10000 (avoids floats in Solidity)
     * @param numSamples      Number of training samples this hospital used
     */
    function logSubmission(
        string memory hospitalId,
        uint256 roundNumber,
        string memory weightsHash,
        uint256 accuracyX10000,
        uint256 numSamples
    ) public {
        uint256 newId = submissions.length;
        uint256 ts = block.timestamp;

        submissions.push(SubmissionEvent({
            id:             newId,
            hospitalId:     hospitalId,
            roundNumber:    roundNumber,
            weightsHash:    weightsHash,
            accuracyX10000: accuracyX10000,
            numSamples:     numSamples,
            timestamp:      ts
        }));

        emit SubmissionLogged(newId, hospitalId, roundNumber, weightsHash, accuracyX10000, numSamples, ts);
    }

    /**
     * Log a FedAvg aggregation completion.
     * Called by Flask after global_model_roundN.pt is saved.
     *
     * @param roundNumber      FL round number
     * @param globalModelHash  SHA-256 of the aggregated global model file
     * @param hospitalsList    Comma-separated list of participating hospital IDs
     * @param totalSamples     Total samples across all hospitals this round
     */
    function logAggregation(
        uint256 roundNumber,
        string memory globalModelHash,
        string memory hospitalsList,
        uint256 totalSamples
    ) public {
        uint256 newId = aggregations.length;
        uint256 ts = block.timestamp;

        aggregations.push(AggregationEvent({
            id:              newId,
            roundNumber:     roundNumber,
            globalModelHash: globalModelHash,
            hospitalsList:   hospitalsList,
            totalSamples:    totalSamples,
            timestamp:       ts
        }));

        emit AggregationLogged(newId, roundNumber, globalModelHash, hospitalsList, totalSamples, ts);
    }

    /**
     * Log a hospital login event.
     * Called by Flask on successful /login.
     *
     * @param hospitalId  Hospital identifier
     */
    function logLogin(string memory hospitalId) public {
        uint256 newId = logins.length;
        uint256 ts = block.timestamp;

        logins.push(LoginEvent({
            id:         newId,
            hospitalId: hospitalId,
            timestamp:  ts
        }));

        emit LoginLogged(newId, hospitalId, ts);
    }

    // ── READ FUNCTIONS ───────────────────────────────────────────────────────

    function getSubmissionCount() public view returns (uint256) {
        return submissions.length;
    }

    function getAggregationCount() public view returns (uint256) {
        return aggregations.length;
    }

    function getLoginCount() public view returns (uint256) {
        return logins.length;
    }

    function getSubmission(uint256 index) public view returns (SubmissionEvent memory) {
        require(index < submissions.length, "Index out of bounds");
        return submissions[index];
    }

    function getAggregation(uint256 index) public view returns (AggregationEvent memory) {
        require(index < aggregations.length, "Index out of bounds");
        return aggregations[index];
    }

    function getLogin(uint256 index) public view returns (LoginEvent memory) {
        require(index < logins.length, "Index out of bounds");
        return logins[index];
    }
}
