import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as iam from "aws-cdk-lib/aws-iam";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as rds from "aws-cdk-lib/aws-rds";

export interface ConversationExtractorProps {
  vpc: ec2.IVpc;
  dbCluster: rds.IDatabaseCluster;
  dbSecretArn: string;
  conversationTableName: string;
  databaseName: string;
}

export class ConversationExtractor extends Construct {
  public readonly extractorFunction: lambda.Function;

  constructor(
    scope: Construct,
    id: string,
    props: ConversationExtractorProps
  ) {
    super(scope, id);

    const { vpc, dbCluster, dbSecretArn, conversationTableName, databaseName } =
      props;

    const stack = cdk.Stack.of(this);

    // Lambda function
    const extractorFunction = new lambda.Function(
      this,
      "ConversationExtractorFunction",
      {
        runtime: lambda.Runtime.PYTHON_3_12,
        handler: "handler.handler",
        code: lambda.Code.fromAsset("../backend/conversation_extractor"),
        timeout: cdk.Duration.minutes(15),
        memorySize: 512,
        vpc,
        vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
        environment: {
          CONVERSATION_TABLE_NAME: conversationTableName,
          AURORA_CLUSTER_ARN: dbCluster.clusterArn,
          AURORA_SECRET_ARN: dbSecretArn,
          DATABASE_NAME: databaseName,
        },
      }
    );

    // DynamoDB permissions
    extractorFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["dynamodb:Scan", "dynamodb:Query"],
        resources: [
          `arn:aws:dynamodb:${stack.region}:${stack.account}:table/${conversationTableName}`,
        ],
      })
    );

    // Bedrock permissions
    extractorFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["bedrock:InvokeModel"],
        resources: [
          `arn:aws:bedrock:${stack.region}::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0`,
        ],
      })
    );

    // Aurora RDS Data API permissions
    extractorFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "rds-data:ExecuteStatement",
          "rds-data:BatchExecuteStatement",
        ],
        resources: [dbCluster.clusterArn],
      })
    );

    // Secrets Manager permission
    extractorFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["secretsmanager:GetSecretValue"],
        resources: [dbSecretArn],
      })
    );

    // EventBridge Rule - every 8 hours
    const rule = new events.Rule(this, "ConversationExtractorSchedule", {
      schedule: events.Schedule.cron({
        minute: "0",
        hour: "*/8",
      }),
    });

    rule.addTarget(new targets.LambdaFunction(extractorFunction));

    this.extractorFunction = extractorFunction;
  }
}
