// compareMongoDocumentCounts.js

import { MongoClient } from 'mongodb';

const selfHostedUri = 'mongodb://localhost:27017'; // replace with your self-hosted MongoDB URI
const atlasUri = 'mongodb+srv://<username>:<password>@cluster0.mongodb.net'; // replace with your MongoDB Atlas URI

const clientSelfHosted = new MongoClient(selfHostedUri);
const clientAtlas = new MongoClient(atlasUri);

async function getNamespaceCounts(client) {
  const namespaceCounts = {};
  const dbList = await client.db().admin().listDatabases();

  for (const { name: dbName } of dbList.databases) {
    // Ignore system databases
    if (dbName.startsWith('system') || ['admin', 'local', 'config'].includes(dbName)) {
      continue;
    }

    const db = client.db(dbName);
    const collections = await db.listCollections().toArray();

    for (const { name: collName } of collections) {
      try {
        const count = await db.collection(collName).countDocuments();
        namespaceCounts[`${dbName}.${collName}`] = count;
      } catch (error) {
        console.error(`Error counting documents in ${dbName}.${collName}:`, error.message);
      }
    }
  }

  return namespaceCounts;
}

async function compareCounts() {
  try {
    await clientSelfHosted.connect();
    await clientAtlas.connect();

    console.log('Fetching document counts from self-hosted MongoDB...');
    const selfHostedCounts = await getNamespaceCounts(clientSelfHosted);

    console.log('Fetching document counts from MongoDB Atlas...');
    const atlasCounts = await getNamespaceCounts(clientAtlas);

    console.log('\nComparison of document counts:');
    let isMatching = true;

    for (const namespace in selfHostedCounts) {
      const selfHostedCount = selfHostedCounts[namespace];
      const atlasCount = atlasCounts[namespace] || 0;

      console.log(`Namespace: ${namespace}`);
      console.log(`Self-hosted count: ${selfHostedCount}`);
      console.log(`Atlas count: ${atlasCount}`);

      if (selfHostedCount !== atlasCount) {
        console.log('Mismatch!');
        isMatching = false;
      } else {
        console.log('Match');
      }
      console.log('---------------------------');
    }

    console.log(isMatching ? '\nResult: PASS - All counts match!' : '\nResult: FAIL - Counts do not match.');

  } catch (error) {
    console.error('Error:', error);
  } finally {
    await clientSelfHosted.close();
    await clientAtlas.close();
  }
}

compareCounts();
