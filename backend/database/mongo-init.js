// MongoDB Initialization Script
// Run with: mongosh distributed_logging mongo-init.js

db = db.getSiblingDB("distributed_logging");

// Create logs collection with schema validation
db.createCollection("logs", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["trace_id", "service_name", "timestamp", "status", "message"],
      properties: {
        trace_id:      { bsonType: "string" },
        service_name:  { bsonType: "string" },
        timestamp:     { bsonType: "string" },
        status:        { bsonType: "string", enum: ["SUCCESS", "ERROR", "WARNING", "INFO"] },
        message:       { bsonType: "string" },
        response_time: { bsonType: ["int", "double", "long"] }
      }
    }
  }
});

// Create indexes
db.logs.createIndex({ trace_id: 1 });
db.logs.createIndex({ service_name: 1 });
db.logs.createIndex({ status: 1 });
db.logs.createIndex({ timestamp: -1 });

print("✅ distributed_logging database initialized successfully");
