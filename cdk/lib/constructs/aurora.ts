import { Construct } from "constructs";
import { CfnOutput, Duration, RemovalPolicy, CustomResource } from "aws-cdk-lib";
import * as rds from "aws-cdk-lib/aws-rds";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as logs from "aws-cdk-lib/aws-logs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as cr from "aws-cdk-lib/custom-resources";
import * as iam from "aws-cdk-lib/aws-iam";
import * as path from "path";

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

    // Lambda function to initialize database with multiple SQL statements
    const initLambda = new lambda.Function(this, "InitFunction", {
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: "index.handler",
      code: lambda.Code.fromAsset(path.join(__dirname, "../../lambda/aurora-init")),
      timeout: Duration.minutes(5),
      environment: {
        CLUSTER_ARN: this.cluster.clusterArn,
        SECRET_ARN: this.secret.secretArn,
        DATABASE_NAME: this.databaseName,
      },
    });

    // Grant permissions to Lambda
    initLambda.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["rds-data:ExecuteStatement"],
        resources: [this.cluster.clusterArn],
      })
    );
    initLambda.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["secretsmanager:GetSecretValue"],
        resources: [this.secret.secretArn],
      })
    );

    // Custom resource provider
    const provider = new cr.Provider(this, "InitProvider", {
      onEventHandler: initLambda,
      logRetention: logs.RetentionDays.ONE_DAY,
    });

    // Custom resource to trigger database initialization
    const initResource = new CustomResource(this, "InitDatabase", {
      serviceToken: provider.serviceToken,
    });

    // Wait for cluster before init
    initResource.node.addDependency(this.cluster);

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
