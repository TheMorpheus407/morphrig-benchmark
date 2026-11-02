// MorphRig - game mode, HUD and the deterministic showcase sequence.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/HUD.h"
#include "MorphRigHUD.generated.h"

class AMorphRigCharacter;
class AMorphRigPerfLogger;

/** Game mode that spawns the Operative and wires the showcase HUD. */
UCLASS()
class MORPHRIG_API AMorphRigGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AMorphRigGameMode();
};

/** HUD with the state panel, the animation browser and the control help. */
UCLASS()
class MORPHRIG_API AMorphRigHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

	/** Set the browser filter text. */
	void SetBrowserFilter(const FString& InFilter) { BrowserFilter = InFilter; }

	/** Set the browser visibility. */
	void SetBrowserVisible(bool bInVisible) { bBrowserVisible = bInVisible; }

	bool IsBrowserVisible() const { return bBrowserVisible; }

	/** The frame time logger of the running level, if there is one. */
	AMorphRigPerfLogger* FindPerfLogger() const;

protected:
	FString BrowserFilter;
	bool bBrowserVisible = false;
};
