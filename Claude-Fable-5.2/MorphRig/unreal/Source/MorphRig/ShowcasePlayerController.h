#pragma once
#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "ShowcasePlayerController.generated.h"

class SShowcasePanel;
class AShowcaseDirector;

/** Keyboard / mouse front end of the showcase. Everything it does goes through AShowcaseDirector::Exec or the state component. */
UCLASS()
class MORPHRIG_API AShowcasePlayerController : public APlayerController
{
	GENERATED_BODY()
public:
	AShowcasePlayerController();
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void PlayerTick(float DeltaTime) override;

	void SetPanelTab(const FString& Name);
	float AimHeight = 130.f;
	static FString HelpText();

private:
	bool JustPressed(const FKey& Key) const { return WasInputKeyJustPressed(Key); }
	bool JustReleased(const FKey& Key) const { return WasInputKeyJustReleased(Key); }
	void HandleHotkeys(AShowcaseDirector* D);
	bool CursorGroundPoint(double PlaneZ, FVector& Out, FVector* OutOrigin = nullptr, FVector* OutDir = nullptr) const;

	TSharedPtr<SShowcasePanel> Panel;
	int32 DragTarget = INDEX_NONE;
	bool bOrbitDrag = false;
	bool bViewportHadFocus = true;
	FVector2D LastMouse = FVector2D::ZeroVector;
};
