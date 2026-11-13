using UnrealBuildTool;

public class MorphRig : ModuleRules
{
	public MorphRig(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] {
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",
			"AnimGraphRuntime",
			"Slate",
			"SlateCore",
			"UMG",
			"RHI",
			"RenderCore",
			"ImageWrapper",
			"Json",
			"JsonUtilities"
		});
	}
}
