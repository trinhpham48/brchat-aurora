import * as cdk from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as iam from "aws-cdk-lib/aws-iam";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as logs from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";
import * as path from "path";

export interface ConversationExtractorStackProps extends cdk.StackProps {
  /**
   * Existing VPC for Lambda
   */
  vpc: ec2.IVpc;

  /**
   * DynamoDB conversation table name
   */
  conversationTableName: string;

  /**
   * DynamoDB conversation table ARN
   */
  conversationTableArn: string;

  /**
   * Aurora cluster ARN
   */
  auroraClusterArn: string;

  /**
   * Aurora secret ARN (for credentials)
   */
  auroraSecretArn: string;

  /**
   * Database name
   */
  databaseName: string;

  /**
   * Bedrock model ID
   */
  bedrockModelId?: string;

  /**
   * Environment prefix
   */
  envPrefix?: string;
}

export class ConversationExtractorStack extends Construct {
  public readonly extractorFunction: lambda.Function;

  constructor(
    scope: Construct,
    id: string,
    props: ConversationExtractorStackProps
  ) {
    super(scope, id);

    const bedrockModelId =
      props.bedrockModelId || "anthropic.claude-3-5-sonnet-20241022-v2:0";

    // Lambda execution role
    const lambdaRole = new iam.Role(this, "ExtractorLambdaRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      description: "Role for Conversation Info Extractor Lambda",
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaVPCAccessExecutionRole"
        ),
      ],
    });

    // DynamoDB permissions
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "dynamodb:Scan",
          "dynamodb:Query",
          "dynamodb:GetItem",
          "dynamodb:BatchGetItem",
        ],
        resources: [
          props.conversationTableArn,
          `${props.conversationTableArn}/index/*`,
        ],
      })
    );

    // Bedrock permissions
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["bedrock:InvokeModel"],
        resources: [
          `arn:aws:bedrock:*::foundation-model/${bedrockModelId.split(":")[0]}`,
        ],
      })
    );

    // Aurora RDS Data API permissions
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "rds-data:ExecuteStatement",
          "rds-data:BatchExecuteStatement",
        ],
        resources: [props.auroraClusterArn],
      })
    );

    // Secrets Manager permission (for Aurora credentials)
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["secretsmanager:GetSecretValue"],
        resources: [props.auroraSecretArn],
      })
    );

    // CloudWatch Logs permissions
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        resources: ["arn:aws:logs:*:*:*"],
      })
    );

    // Lambda function
    this.extractorFunction = new lambda.Function(this, "ExtractorFunction", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "handler.handler",
      code: lambda.Code.fromAsset(
        path.join(__dirname, "../../backend/conversation_extractor")
      ),
      role: lambdaRole,
      timeout: cdk.Duration.minutes(15), // Max timeout for batch processing
      memorySize: 512,
      vpc: props.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      environment: {
        CONVERSATION_TABLE_NAME: props.conversationTableName,
        AURORA_CLUSTER_ARN: props.auroraClusterArn,
        AURORA_SECRET_ARN: props.auroraSecretArn,
        DATABASE_NAME: props.databaseName,
        BEDROCK_MODEL_ID: bedrockModelId,
        POWERTOOLS_SERVICE_NAME: "conversation-extractor",
        POWERTOOLS_LOG_LEVEL: "INFO",
        LOG_LEVEL: "INFO",
      },
      description: "Extract structured info from conversations using Bedrock",
      logRetention: logs.RetentionDays.ONE_MONTH,
    });

    // EventBridge Rule - Every 8 hours
    const scheduleRule = new events.Rule(this, "ExtractionSchedule", {
      // Run at 00:00, 08:00, 16:00 UTC every day
      schedule: events.Schedule.cron({
        minute: "0",
        hour: "0,8,16",
      }),
      description: "Trigger conversation extraction every 8 hours",
    });

    // Add Lambda as target
    scheduleRule.addTarget(
      new targets.LambdaFunction(this.extractorFunction, {
        retryAttempts: 2,
      })
    );

    // CloudWatch Log Group
    new logs.LogGroup(this, "ExtractorLogGroup", {
      logGroupName: `/aws/lambda/${this.extractorFunction.functionName}`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Outputs
    new cdk.CfnOutput(this, "ExtractorFunctionName", {
      value: this.extractorFunction.functionName,
      description: "Conversation Extractor Lambda Function Name",
      exportName: `${props.envPrefix || ""}ConversationExtractorFunctionName`,
    });

    new cdk.CfnOutput(this, "ExtractorFunctionArn", {
      value: this.extractorFunction.functionArn,
      description: "Conversation Extractor Lambda Function ARN",
      exportName: `${props.envPrefix || ""}ConversationExtractorFunctionArn`,
    });

    new cdk.CfnOutput(this, "ExtractionSchedule", {
      value: "Every 8 hours (00:00, 08:00, 16:00 UTC)",
      description: "Extraction schedule",
    });
  }
}
