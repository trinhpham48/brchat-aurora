import { Construct } from "constructs";
import { CfnOutput, Duration, RemovalPolicy } from "aws-cdk-lib";
import * as rds from "aws-cdk-lib/aws-rds";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as logs from "aws-cdk-lib/aws-logs";
import { AwsCustomResource, AwsCustomResourcePolicy, PhysicalResourceId } from "aws-cdk-lib/custom-resources";
import * as iam from "aws-cdk-lib/aws-iam";

export interface AuroraProps {
  readonly vpc?: ec2.IVpc;
  readonly enableReplicas?: boolean;
  readonly envPrefix?: string;
}

export class Aurora extends Construct {
  public readonly cluster: rds.DatabaseCluster;
  public readonly clusterEndpoint: string;
  public readonly secret: secretsmanager.ISecret;
  public readonly connections: ec2.Connections;
  public readonly vpc: ec2.IVpc;
  public readonly databaseName: string;

  constructor(scope: Construct, id: string, props?: AuroraProps) {
    super(scope, id);

    this.databaseName = "bedrockchat";

    // Create VPC if not provided (isolated for Aurora)
    this.vpc = props?.vpc ?? new ec2.Vpc(this, "AuroraVpc", {
      maxAzs: 2,
      natGateways: 1,
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: "Private",
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
        {
          cidrMask: 24,
          name: "Public",
          subnetType: ec2.SubnetType.PUBLIC,
        },
      ],
    });

    // Security group for Aurora
    const securityGroup = new ec2.SecurityGroup(this, "AuroraSecurityGroup", {
      vpc: this.vpc,
      description: "Security group for Aurora PostgreSQL cluster",
      allowAllOutbound: true,
    });

    // Allow Lambda to connect
    securityGroup.addIngressRule(
      ec2.Peer.ipv4(this.vpc.vpcCidrBlock),
      ec2.Port.tcp(5432),
      "Allow PostgreSQL access from VPC"
    );

    // Aurora Serverless v2 cluster
    this.cluster = new rds.DatabaseCluster(this, "Cluster", {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_16_1,
      }),
      writer: rds.ClusterInstance.serverlessV2("Writer", {
        enablePerformanceInsights: true,
        performanceInsightRetention: rds.PerformanceInsightRetention.DEFAULT,
      }),
      readers: props?.enableReplicas
        ? [
            rds.ClusterInstance.serverlessV2("Reader", {
              scaleWithWriter: true,
              enablePerformanceInsights: true,
            }),
          ]
        : [],
      serverlessV2MinCapacity: 0.5, // Minimum ACUs
      serverlessV2MaxCapacity: 2, // Maximum ACUs
      vpc: this.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [securityGroup],
      defaultDatabaseName: this.databaseName,
      removalPolicy: RemovalPolicy.SNAPSHOT,
      backup: {
        retention: Duration.days(7),
        preferredWindow: "03:00-04:00",
      },
      preferredMaintenanceWindow: "sun:04:00-sun:05:00",
      cloudwatchLogsExports: ["postgresql"],
      cloudwatchLogsRetention: logs.RetentionDays.ONE_WEEK,
      storageEncrypted: true,
      deletionProtection: false, // Set to true in production
    });

    this.clusterEndpoint = this.cluster.clusterEndpoint.socketAddress;
    this.secret = this.cluster.secret!;
    this.connections = this.cluster.connections;

    // Enable Data API for serverless access
    const cfnCluster = this.cluster.node.defaultChild as rds.CfnDBCluster;
    cfnCluster.enableHttpEndpoint = true;

    // Wait for cluster to be available before initializing
    const waitForCluster = new AwsCustomResource(this, "WaitForCluster", {
      onCreate: {
        service: "RDS",
        action: "describeDBClusters",
        parameters: {
          DBClusterIdentifier: this.cluster.clusterIdentifier,
        },
        physicalResourceId: PhysicalResourceId.of("WaitForCluster"),
      },
      policy: AwsCustomResourcePolicy.fromStatements([
        new iam.PolicyStatement({
          actions: ["rds:DescribeDBClusters"],
          resources: ["*"],
        }),
      ]),
    });
    waitForCluster.node.addDependency(this.cluster);

    // Custom resource to initialize database with pgvector extension
    const initDbFunction = new AwsCustomResource(this, "InitDatabase", {
      onCreate: {
        service: "RDSDataService",
        action: "executeStatement",
        parameters: {
          resourceArn: this.cluster.clusterArn,
          secretArn: this.secret.secretArn,
          database: this.databaseName,
          sql: `
            -- Enable required extensions
            CREATE EXTENSION IF NOT EXISTS vector;
            CREATE EXTENSION IF NOT EXISTS pg_trgm;
            CREATE EXTENSION IF NOT EXISTS btree_gin;
            
            -- Create bot_vectors table for bot search
            CREATE TABLE IF NOT EXISTS bot_vectors (
              bot_id VARCHAR(255) PRIMARY KEY,
              title TEXT NOT NULL,
              description TEXT,
              instruction TEXT,
              owner_user_id VARCHAR(255),
              embedding vector(1024),
              create_time BIGINT,
              last_used_time BIGINT,
              sync_status VARCHAR(50) DEFAULT 'SUCCEEDED',
              shared_scope VARCHAR(50) DEFAULT 'PRIVATE',
              is_pinned BOOLEAN DEFAULT FALSE,
              allowed_users TEXT[],
              search_vector tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(instruction, '')), 'C')
              ) STORED,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Indexes for bot search
            CREATE INDEX IF NOT EXISTS bot_vectors_embedding_idx 
              ON bot_vectors USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
            CREATE INDEX IF NOT EXISTS bot_vectors_search_idx 
              ON bot_vectors USING GIN(search_vector);
            CREATE INDEX IF NOT EXISTS bot_vectors_title_trgm_idx 
              ON bot_vectors USING GIN(title gin_trgm_ops);
            CREATE INDEX IF NOT EXISTS bot_vectors_owner_idx 
              ON bot_vectors(owner_user_id);
            CREATE INDEX IF NOT EXISTS bot_vectors_shared_idx 
              ON bot_vectors(shared_scope);
            
            -- Create conversation_vectors table
            CREATE TABLE IF NOT EXISTS conversation_vectors (
              conversation_id VARCHAR(255) PRIMARY KEY,
              user_id VARCHAR(255) NOT NULL,
              title TEXT NOT NULL,
              title_embedding vector(1024),
              bot_id VARCHAR(255),
              last_updated_time BIGINT,
              message_count INTEGER DEFAULT 0,
              search_vector tsvector GENERATED ALWAYS AS (
                to_tsvector('english', coalesce(title, ''))
              ) STORED,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Indexes for conversation search
            CREATE INDEX IF NOT EXISTS conversation_vectors_embedding_idx 
              ON conversation_vectors USING ivfflat (title_embedding vector_cosine_ops) WITH (lists = 100);
            CREATE INDEX IF NOT EXISTS conversation_vectors_search_idx 
              ON conversation_vectors USING GIN(search_vector);
            CREATE INDEX IF NOT EXISTS conversation_vectors_user_idx 
              ON conversation_vectors(user_id);
            CREATE INDEX IF NOT EXISTS conversation_vectors_bot_idx 
              ON conversation_vectors(bot_id);
          `,
        },
        physicalResourceId: PhysicalResourceId.of("InitDatabase"),
      },
      policy: AwsCustomResourcePolicy.fromStatements([
        new iam.PolicyStatement({
          actions: ["rds-data:ExecuteStatement"],
          resources: [this.cluster.clusterArn],
        }),
        new iam.PolicyStatement({
          actions: ["secretsmanager:GetSecretValue"],
          resources: [this.secret.secretArn],
        }),
      ]),
    });

    // Wait for cluster to be available before running init
    initDbFunction.node.addDependency(waitForCluster);

    // Outputs
    new CfnOutput(this, "ClusterEndpoint", {
      value: this.clusterEndpoint,
      description: "Aurora cluster endpoint",
    });

    new CfnOutput(this, "ClusterArn", {
      value: this.cluster.clusterArn,
      description: "Aurora cluster ARN",
    });

    new CfnOutput(this, "SecretArn", {
      value: this.secret.secretArn,
      description: "Aurora credentials secret ARN",
    });

    new CfnOutput(this, "DatabaseName", {
      value: this.databaseName,
      description: "Aurora database name",
    });
  }
}
