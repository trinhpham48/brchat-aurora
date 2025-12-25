import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as iam from "aws-cdk-lib/aws-iam";

export interface ConversationExtractorProps {
  conversationTableName: string;
}

export class ConversationExtractor extends Construct {
  public readonly function: lambda.Function;

  constructor(scope: Construct, id: string, props: ConversationExtractorProps) {
    super(scope, id);

    const stack = cdk.Stack.of(this);

    this.function = new lambda.Function(this, "Function", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "index.handler",
      code: lambda.Code.fromAsset("lambda/conversation-extractor"),
      timeout: cdk.Duration.minutes(3),
      memorySize: 256,
      environment: {
        TABLE_NAME: props.conversationTableName,
      },
    });

    // DynamoDB read
    this.function.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["dynamodb:GetItem", "dynamodb:Query"],
        resources: [
          `arn:aws:dynamodb:${stack.region}:${stack.account}:table/${props.conversationTableName}`,
          `arn:aws:dynamodb:${stack.region}:${stack.account}:table/${props.conversationTableName}/index/*`,
        ],
      })
    );

    // Bedrock invoke
    this.function.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:InvokeModel"],
        resources: [
          `arn:aws:bedrock:${stack.region}::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0`,
        ],
      })
    );
  }
}
