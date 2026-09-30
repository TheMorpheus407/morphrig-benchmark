#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "MorphHUD.generated.h"

/** Canvas overlay: state / clip / time / speed / layers, marker timeline, event log, key help. */
UCLASS()
class MORPHRIG_API AMorphHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

private:
	void Line(float X, float& Y, const FString& S, const FLinearColor& C = FLinearColor(0.85f, 0.9f, 0.95f), float Scale = 1.f);
	void DrawTimeline(float X, float Y, float W);
	float SmoothFps = 60.f;
	float SmoothMs = 16.f;
};
