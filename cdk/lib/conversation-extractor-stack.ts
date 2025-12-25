import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as iam from "aws-cdk-lib/aws-iam";

export interface ConversationExtractorProps {
  conversationTableName: string;
}

export class ConversationExtractor extends Construct {
  public readonly extractorFunction: lambda.Function;

  constructor(
    scope: Construct,
    id: string,
    props: ConversationExtractorProps
  ) {
    super(scope, id);

    const { conversationTableName } = props;
    const stack = cdk.Stack.of(this);

    // Lambda function - simple standalone
    const extractorFunction = new lambda.Function(
      this,
      "ConversationExtractorFunction",
      {
        runtime: lambda.Runtime.PYTHON_3_12,
        handler: "handler.handler",
        code: lambda.Code.fromAsset("../backend/conversation_extractor"),
        timeout: cdk.Duration.minutes(5),
        memorySize: 256,
        environment: {
          CONVERSATION_TABLE_NAME: conversationTableName,
        },
      }
    );

    // DynamoDB read permissions
    extractorFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["dynamodb:GetItem", "dynamodb:Query"],
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

    this.extractorFunction = extractorFunction;
  }
}
